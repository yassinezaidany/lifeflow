"""Rule-based insights: short, actionable observations computed from the user's own data.

Every number comes from the ProgressEngine results passed in (or from simple counts of
entries / planned activities); nothing is stored and nothing leaves the server.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from django.urls import reverse
from django.utils.dates import WEEKDAYS
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.core.dates import user_today
from apps.planner import services as planner
from apps.planner.models import PlannedActivity
from apps.tracking.models import ChallengeEntry

from .progress import ProgressStatus


@dataclass
class Insight:
    kind: str          # machine name, stable for tests
    tone: str          # success | warning | danger | info (maps to the tone-* classes)
    icon: str
    title: str
    text: str
    priority: int
    url: str = ""
    action: str = ""


def _streak_label(n: int, unit: str) -> str:
    if unit == "week":
        return ngettext("%(n)s week", "%(n)s weeks", n) % {"n": n}
    if unit == "month":
        return ngettext("%(n)s month", "%(n)s months", n) % {"n": n}
    return ngettext("%(n)s day", "%(n)s days", n) % {"n": n}


def _challenge_insights(cards) -> list[Insight]:
    out: list[Insight] = []
    behind = []
    for card in cards:
        c, r = card["challenge"], card["progress"]
        if r.goal_obj is None or c.status != "active":
            continue
        url = reverse("challenges:detail", args=[c.pk])
        today = r.today or {}
        limit = r.goal_obj.is_limit

        if today.get("limit") and today.get("status") == "over":
            out.append(Insight("limit_over", "danger", "triangle-alert", _("Limit exceeded today"),
                               _("%(name)s is over today's limit (%(actual)s / %(target)s).") % {
                                   "name": c.name, "actual": today["display"]["period_actual"],
                                   "target": today["display"]["period_target"]},
                               95, url, _("Open")))
        elif (not limit and r.current_streak >= 3 and today.get("type") == "active"
              and not today.get("done") and r.streak_unit == "day"):
            out.append(Insight("streak_at_risk", "warning", "flame", _("Keep your streak alive"),
                               _("Your %(streak)s streak on %(name)s is waiting for today's result.") % {
                                   "streak": _streak_label(r.current_streak, r.streak_unit), "name": c.name},
                               90, url, _("Record")))

        if r.status == ProgressStatus.BEHIND and not limit and r.gap is not None and r.expected:
            behind.append((r.gap / r.expected, c, r, url))

        for m in r.milestones:
            if not m["reached"] and m["progress"] >= 80:
                out.append(Insight("milestone_close", "info", "trophy", _("Milestone in sight"),
                                   _("%(name)s: %(progress)s%% of the way to “%(title)s”.") % {
                                       "name": c.name, "progress": round(m["progress"]), "title": m["title"]},
                                   60, url, _("Open")))
                break

        if r.status == ProgressStatus.AHEAD and not limit and r.progress is not None and r.progress < 100:
            out.append(Insight("ahead", "success", "trending-up", _("Ahead of schedule"),
                               _("%(name)s is ahead of plan — nice work.") % {"name": c.name}, 30, url, _("Open")))

    if behind:
        _ratio, c, r, url = min(behind, key=lambda item: item[0])
        amount = f"{r.fmt(abs(r.gap))} {r.unit}".strip()
        out.append(Insight("behind", "warning", "calendar-plus", _("Needs attention"),
                           _("%(name)s is %(amount)s behind. Planning a session in the planner makes it easier to catch up.") % {
                               "name": c.name, "amount": amount},
                           80, reverse("planner:week"), _("Plan a session")))
    return out


def _planner_trend(user, today) -> Insight | None:
    start = today - timedelta(days=13)
    planner.ensure_occurrences(user, start, today - timedelta(days=1))
    acts = list(PlannedActivity.objects.filter(user=user, date__range=(start, today - timedelta(days=1))))
    split = today - timedelta(days=7)
    previous = planner.summarize([a for a in acts if a.date < split], user)
    recent = planner.summarize([a for a in acts if a.date >= split], user)
    if previous["planned"] < 3 or recent["planned"] < 3:
        return None
    before, now = previous["completion_rate"] or 0, recent["completion_rate"] or 0
    diff = round(now - before)
    if diff >= 15:
        return Insight("planner_up", "success", "trending-up", _("Your planning is paying off"),
                       _("You completed %(now)s%% of planned activities this week, up from %(before)s%%.") % {
                           "now": round(now), "before": round(before)}, 50, reverse("planner:week"), _("Planner"))
    if diff <= -15:
        return Insight("planner_down", "warning", "trending-down", _("Planner follow-through dropped"),
                       _("You completed %(now)s%% of planned activities this week, down from %(before)s%%. Try planning fewer, shorter blocks.") % {
                           "now": round(now), "before": round(before)}, 70, reverse("planner:week"), _("Planner"))
    return None


def _entry_patterns(user, today, has_active: bool) -> list[Insight]:
    out = []
    dates = list(ChallengeEntry.objects.filter(user=user, date__range=(today - timedelta(days=55), today))
                 .values_list("date", flat=True))
    if has_active and dates and max(dates) <= today - timedelta(days=3):
        days = (today - max(dates)).days
        out.append(Insight("inactive", "info", "history", _("Welcome back"),
                           _("Nothing recorded for %(days)s days. One small entry today restarts the habit.") % {"days": days},
                           85, reverse("dashboard:today"), _("Today")))
    if len(dates) >= 10:
        counts = Counter(d.weekday() for d in dates)
        best, best_count = counts.most_common(1)[0]
        if best_count >= 1.5 * (len(dates) / 7):
            out.append(Insight("best_weekday", "info", "calendar-check", _("Your strongest day"),
                               _("You record the most on %(day)s. Schedule your hardest sessions then.") % {
                                   "day": WEEKDAYS[best]}, 20))
    return out


def build_insights(user, cards, limit: int | None = None) -> list[Insight]:
    """`cards` are dashboard-style rows ({"challenge", "progress"}) evaluated over the whole challenge."""
    today = user_today(user)
    insights = _challenge_insights(cards)
    trend = _planner_trend(user, today)
    if trend:
        insights.append(trend)
    insights += _entry_patterns(user, today, has_active=any(c["challenge"].status == "active" for c in cards))
    insights.sort(key=lambda i: -i.priority)
    return insights[:limit] if limit else insights
