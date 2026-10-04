"""Goal semantics: periods, per-entry measurement and human descriptions."""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.challenges.models import Goal, TrackingField
from apps.core.dates import format_minutes, week_start_for

EPSILON = 1e-9


@dataclass
class EntryData:
    """Lightweight, query-free representation of an entry for the engine."""

    id: int
    date: date
    numbers: dict[int, float | None] = field(default_factory=dict)
    bools: dict[int, bool | None] = field(default_factory=dict)
    times: dict[int, object] = field(default_factory=dict)


def goal_for_day(goals: list[Goal], day: date) -> Goal | None:
    found = None
    for g in goals:
        if g.effective_from <= day and (g.effective_to is None or day <= g.effective_to):
            found = g
    if found is None and goals and day < goals[0].effective_from:
        found = goals[0]
    return found


def period_bounds(day: date, period: str, week_starts_on: int = 0) -> tuple[date, date]:
    if period == Goal.Period.DAILY:
        return day, day
    if period == Goal.Period.WEEKLY:
        first = week_start_for(day, week_starts_on)
        return first, first + timedelta(days=6)
    if period == Goal.Period.MONTHLY:
        last = calendar.monthrange(day.year, day.month)[1]
        return day.replace(day=1), day.replace(day=last)
    raise ValueError(f"Period {period} has no calendar bounds")


def entry_value(goal: Goal, entry: EntryData) -> float:
    """Raw measured value of an entry for the goal's metric."""
    metric = goal.metric
    if metric is None:
        return 1.0
    if metric.field_type == TrackingField.FieldType.BOOLEAN:
        return 1.0 if entry.bools.get(metric.pk) else 0.0
    if metric.field_type == TrackingField.FieldType.TIME:
        recorded, threshold = entry.times.get(metric.pk), goal.time_threshold
        if recorded is None or threshold is None:
            return 0.0
        ok = recorded >= threshold if goal.time_comparison == "after" else recorded <= threshold
        return 1.0 if ok else 0.0
    value = entry.numbers.get(metric.pk)
    return float(value) if value is not None else 0.0


def entry_contribution(goal: Goal, entry: EntryData) -> float:
    """How much an entry adds to the goal's actual value.

    SUM   -> the measured value (only if it reaches `min_per_entry`, when set)
    COUNT -> 1 if the entry qualifies (value > 0, or >= `min_per_entry`)
    """
    value = entry_value(goal, entry)
    minimum = float(goal.min_per_entry) if goal.min_per_entry is not None else None
    qualifies = value >= minimum - EPSILON if minimum is not None else value > EPSILON
    if goal.aggregation == Goal.Aggregation.COUNT:
        return 1.0 if qualifies else 0.0
    return value if qualifies else 0.0


def format_value(value: float | None, goal: Goal | None) -> str:
    if value is None:
        return "—"
    if goal is not None and goal.is_duration:
        return format_minutes(value)
    if abs(value - round(value)) < 0.005:
        return f"{int(round(value))}"
    return f"{value:.1f}"


def _counted_unit(goal: Goal, n: float) -> str:
    """Pluralised unit for count-like goals; free-text units are returned as typed."""
    count = 1 if abs(n - 1) < EPSILON else 2
    if goal.metric is not None and goal.metric.field_type in (TrackingField.FieldType.BOOLEAN, TrackingField.FieldType.TIME):
        return ngettext("day", "days", count)
    if goal.metric is None or goal.aggregation == Goal.Aggregation.COUNT:
        return ngettext("session", "sessions", count)
    return goal.metric.display_unit


def describe_goal(goal: Goal | None) -> str:
    if goal is None:
        return _("No goal defined")
    target = float(goal.target)
    is_boolean = goal.metric is not None and goal.metric.field_type == TrackingField.FieldType.BOOLEAN
    if goal.is_time_goal and goal.time_threshold:
        when = (_("after %(t)s") if goal.time_comparison == "after" else _("before %(t)s")) % {"t": goal.time_threshold.strftime("%H:%M")}
        if goal.period == Goal.Period.DAILY and abs(target - 1) < EPSILON:
            return f"{goal.metric.label} {when} · " + _("every scheduled day")
        return f"{goal.metric.label} {when} · {format_value(target, None)} {_counted_unit(goal, target)} " + {
            Goal.Period.DAILY: _("/ day"), Goal.Period.WEEKLY: _("/ week"), Goal.Period.MONTHLY: _("/ month"), Goal.Period.TOTAL: _("in total"),
        }[goal.period]
    if is_boolean and goal.period == Goal.Period.DAILY and abs(target - 1) < EPSILON:
        return _("Every scheduled day")
    amount = format_value(target, goal)
    unit = "" if goal.is_duration else f" {_counted_unit(goal, target)}"
    period = {
        Goal.Period.DAILY: _("/ day"),
        Goal.Period.WEEKLY: _("/ week"),
        Goal.Period.MONTHLY: _("/ month"),
        Goal.Period.TOTAL: _("in total"),
    }[goal.period]
    text = f"{amount}{unit} {period}"
    if goal.min_per_entry:
        minimum = format_value(float(goal.min_per_entry), goal if goal.metric and goal.metric.field_type == TrackingField.FieldType.DURATION else None)
        metric_unit = "" if goal.metric and goal.metric.field_type == TrackingField.FieldType.DURATION else (f" {goal.metric.display_unit}" if goal.metric else "")
        text += " · " + _("min. %(value)s per entry") % {"value": f"{minimum}{metric_unit}"}
    return text
