"""
Progress engine.

Vocabulary
----------
* **Bucket**: one evaluation period of a goal version (a day for daily goals, a
  calendar week / month for weekly / monthly goals). Each bucket has a *target*.
* **Eligible day**: an ACTIVE day (scheduled, not a rest day, not paused).
* **Day share**: a bucket's target spread evenly over its eligible days. It drives
  *Expected* (pace) and windowed goals (monthly reports) with one uniform rule.

Key rules
---------
* Expected is measured against *fully elapsed* days: today's work counts in
  Actual immediately, but today only enters Expected once the day is over.
* Weekly / monthly targets are prorated for partial periods (challenge start/end,
  pauses) by calendar days; rest days do not reduce a weekly target, they only
  change on which days the work is expected.
* Goals and schedules are versioned: each day is evaluated with the versions in
  force on that day.
* A planned activity never feeds the engine; only confirmed entries do.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable

from django.db.models import Prefetch, Q

from apps.challenges.models import Challenge, Goal, RestDay
from apps.core.dates import daterange, user_today
from apps.tracking.models import ChallengeEntry, EntryFieldValue

from .goals import (
    EPSILON,
    EntryData,
    describe_goal,
    entry_contribution,
    format_value,
    goal_for_day,
    period_bounds,
)
from .schedules import ChallengeCalendar, DayType
from .statistics import compute_statistics
from .status import ProgressStatus, compute_status
from .streaks import StreakUnit, best_streak, current_streak

STREAK_UNITS = {
    Goal.Period.DAILY: "day",
    Goal.Period.WEEKLY: "week",
    Goal.Period.MONTHLY: "month",
    Goal.Period.TOTAL: "day",
}


@dataclass
class Bucket:
    goal: Goal
    start: date
    end: date
    days: list[date] = field(default_factory=list)
    eligible: list[date] = field(default_factory=list)
    nonpaused: int = 0
    target: float = 0.0
    actual: float = 0.0
    due: bool = False

    @property
    def achieved(self) -> bool:
        return self.target > EPSILON and self.actual >= self.target - EPSILON

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "target": round(self.target, 2),
            "actual": round(self.actual, 2),
            "achieved": self.achieved,
            "due": self.due,
        }


@dataclass
class DayPoint:
    date: date
    type: DayType
    actual: float
    target: float
    status: str  # done | partial | missed | pending | future | rest | paused | empty | outside

    def as_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "type": self.type.value,
            "actual": round(self.actual, 2),
            "target": round(self.target, 2),
            "status": self.status,
        }


@dataclass
class ProgressResult:
    challenge_id: int
    goal_obj: Goal | None
    goal: float
    actual: float
    expected: float | None
    remaining: float
    progress: float | None
    gap: float | None
    status: ProgressStatus
    completion_rate: float | None
    completed_periods: int
    due_periods: int
    current_streak: int
    best_streak: int
    streak_unit: str
    average: float | None
    period: str | None
    target: float | None
    window: tuple[date, date]
    today: dict
    days: list[DayPoint] = field(default_factory=list)
    buckets: list[dict] = field(default_factory=list)
    statistics: dict = field(default_factory=dict)
    milestones: list[dict] = field(default_factory=list)

    # --- presentation helpers --------------------------------------------------------
    @property
    def unit(self) -> str:
        return "" if self.goal_obj is None or self.goal_obj.is_duration else self.goal_obj.unit_label

    @property
    def is_duration(self) -> bool:
        return bool(self.goal_obj and self.goal_obj.is_duration)

    @property
    def goal_description(self) -> str:
        return describe_goal(self.goal_obj)

    @property
    def progress_capped(self) -> float:
        return max(0.0, min(self.progress or 0.0, 100.0))

    def fmt(self, value: float | None) -> str:
        return format_value(value, self.goal_obj)

    @property
    def display(self) -> dict:
        gap = None
        if self.gap is not None:
            sign = "+" if self.gap > EPSILON else ("−" if self.gap < -EPSILON else "±")
            gap = f"{sign}{self.fmt(abs(self.gap))}"
        return {
            "goal": self.fmt(self.goal),
            "actual": self.fmt(self.actual),
            "expected": self.fmt(self.expected),
            "remaining": self.fmt(self.remaining),
            "gap": gap or "—",
            "average": self.fmt(self.average),
            "target": self.fmt(self.target),
            "unit": self.unit,
        }

    def as_dict(self, include_series: bool = True) -> dict:
        data = {
            "challenge_id": self.challenge_id,
            "goal_description": self.goal_description,
            "period": self.period,
            "unit": self.unit,
            "is_duration": self.is_duration,
            "target": _r(self.target),
            "goal": _r(self.goal),
            "actual": _r(self.actual),
            "expected": _r(self.expected),
            "remaining": _r(self.remaining),
            "progress": _r(self.progress, 1),
            "gap": _r(self.gap),
            "status": self.status.value,
            "completion_rate": _r(self.completion_rate, 1),
            "completed_periods": self.completed_periods,
            "due_periods": self.due_periods,
            "current_streak": self.current_streak,
            "best_streak": self.best_streak,
            "longest_streak": self.best_streak,
            "streak_unit": self.streak_unit,
            "average": _r(self.average),
            "window": [self.window[0].isoformat(), self.window[1].isoformat()],
            "today": self.today,
            "display": self.display,
            "milestones": self.milestones,
            "statistics": self.statistics,
        }
        if include_series:
            data["days"] = [d.as_dict() for d in self.days]
            data["buckets"] = self.buckets
        return data


def _r(value, digits: int = 2):
    return None if value is None else round(value, digits)


class ProgressEngine:
    """Evaluate challenges for one user at a given date (default: today in the user's TZ).

    `day_closed=True` treats `as_of` as fully elapsed (used for past-period reports).
    """

    def __init__(self, user, as_of: date | None = None, day_closed: bool = False):
        self.user = user
        self.as_of = as_of or user_today(user)
        self.day_closed = day_closed
        profile = getattr(user, "profile", None)
        self.week_start = profile.week_start if profile is not None else 0

    # --- data loading ----------------------------------------------------------------------
    @staticmethod
    def prefetch(queryset):
        return queryset.select_related("category").prefetch_related(
            Prefetch("goals", queryset=Goal.objects.select_related("metric")),
            "schedules",
            "pauses",
            "milestones",
        )

    def _load_entries(self, challenges: list[Challenge]) -> dict[int, list[EntryData]]:
        ids = [c.pk for c in challenges]
        min_start = min(c.start_date for c in challenges)
        metric_ids = {g.metric_id for c in challenges for g in c._prefetched("goals") if g.metric_id}
        entries: dict[int, EntryData] = {}
        by_challenge: dict[int, list[EntryData]] = defaultdict(list)
        rows = ChallengeEntry.objects.filter(
            challenge_id__in=ids, date__gte=min_start, date__lte=self.as_of
        ).values_list("id", "challenge_id", "date")
        for entry_id, challenge_id, day in rows:
            data = EntryData(id=entry_id, date=day)
            entries[entry_id] = data
            by_challenge[challenge_id].append(data)
        if metric_ids and entries:
            values = EntryFieldValue.objects.filter(
                entry__challenge_id__in=ids,
                entry__date__gte=min_start,
                entry__date__lte=self.as_of,
                field_id__in=metric_ids,
            ).values_list("entry_id", "field_id", "value_number", "value_bool")
            for entry_id, field_id, number, boolean in values:
                data = entries.get(entry_id)
                if data is not None:
                    data.numbers[field_id] = float(number) if number is not None else None
                    data.bools[field_id] = boolean
        return by_challenge

    def _load_rest_days(self, challenges: list[Challenge]) -> dict[int | None, set[date]]:
        ids = [c.pk for c in challenges]
        min_start = min(c.start_date for c in challenges)
        rest: dict[int | None, set[date]] = defaultdict(set)
        rows = RestDay.objects.filter(user_id=self.user.pk, date__gte=min_start).filter(
            Q(challenge_id__in=ids) | Q(challenge__isnull=True)
        )
        for challenge_id, day in rows.values_list("challenge_id", "date"):
            rest[challenge_id].add(day)
        return rest

    # --- public API --------------------------------------------------------------------------
    def evaluate(self, challenge: Challenge, *, include_series: bool = False, window: tuple[date, date] | None = None) -> ProgressResult:
        return self.evaluate_many([challenge], include_series=include_series, window=window)[challenge.pk]

    def evaluate_many(
        self,
        challenges: Iterable[Challenge],
        *,
        include_series: bool = False,
        window: tuple[date, date] | None = None,
    ) -> dict[int, ProgressResult]:
        challenges = list(challenges)
        if not challenges:
            return {}
        entries = self._load_entries(challenges)
        rest = self._load_rest_days(challenges)
        global_rest = rest.get(None, set())
        return {
            c.pk: self._evaluate(c, entries.get(c.pk, []), global_rest | rest.get(c.pk, set()), include_series, window)
            for c in challenges
        }

    # --- core algorithm -------------------------------------------------------------------
    def _evaluate(self, challenge, entries, rest_days, include_series, window) -> ProgressResult:
        goals = challenge._prefetched("goals")
        cal = ChallengeCalendar(challenge, rest_days, self.as_of)
        start, end, as_of = challenge.start_date, cal.end, self.as_of

        expected_through = as_of if self.day_closed else as_of - timedelta(days=1)
        eval_end = as_of
        if end is not None:
            expected_through = min(expected_through, end)
            eval_end = min(eval_end, end)
        ref_day = max(as_of, start) if end is None else min(max(as_of, start), end)
        goal = goal_for_day(goals, ref_day)

        if goal is None:
            return self._empty(challenge, start, ref_day)

        is_total = goal.period == Goal.Period.TOTAL
        if end is not None:
            horizon_end = end
        elif is_total:
            horizon_end = max(eval_end, start)
        else:
            horizon_end = period_bounds(ref_day, goal.period, self.week_start)[1]
        if window is not None and end is None:
            horizon_end = max(horizon_end, window[1])

        # 1. Classify days and build buckets ------------------------------------------------
        day_types: dict[date, DayType] = {}
        buckets: dict[tuple, Bucket] = {}
        day_bucket: dict[date, Bucket] = {}
        day_share: dict[date, float] = defaultdict(float)
        for day in daterange(start, horizon_end):
            day_types[day] = cal.classify(day)

        if is_total:
            eligible = [d for d, t in day_types.items() if t == DayType.ACTIVE]
            if end is not None and eligible:
                share = float(goal.target) / len(eligible)
                for d in eligible:
                    day_share[d] = share
        else:
            for day, dtype in day_types.items():
                g = goal_for_day(goals, day)
                if g is None or g.period == Goal.Period.TOTAL:
                    continue
                p_start, p_end = period_bounds(day, g.period, self.week_start)
                bucket = buckets.get((g.pk, p_start))
                if bucket is None:
                    bucket = buckets[(g.pk, p_start)] = Bucket(goal=g, start=p_start, end=p_end)
                bucket.days.append(day)
                if dtype == DayType.ACTIVE:
                    bucket.eligible.append(day)
                if dtype != DayType.PAUSED:
                    bucket.nonpaused += 1
                day_bucket[day] = bucket
            for bucket in buckets.values():
                if not bucket.eligible:
                    bucket.target = 0.0
                elif bucket.goal.period == Goal.Period.DAILY:
                    bucket.target = float(bucket.goal.target)
                else:
                    period_len = (bucket.end - bucket.start).days + 1
                    bucket.target = float(bucket.goal.target) * bucket.nonpaused / period_len
                if bucket.eligible:
                    share = bucket.target / len(bucket.eligible)
                    for d in bucket.eligible:
                        day_share[d] = share
                bucket.due = bucket.days[-1] <= expected_through

        # 2. Apply entries -------------------------------------------------------------------
        day_actual: dict[date, float] = defaultdict(float)
        day_entries: dict[date, int] = defaultdict(int)
        for entry in entries:
            if entry.date < start or entry.date > eval_end:
                continue
            if is_total:
                contribution = entry_contribution(goal, entry)
            else:
                bucket = day_bucket.get(entry.date)
                if bucket is None:
                    continue
                contribution = entry_contribution(bucket.goal, entry)
                bucket.actual += contribution
            day_actual[entry.date] += contribution
            day_entries[entry.date] += 1

        # 3. Headline numbers (optionally restricted to a window) ----------------------------
        w_start = max(window[0], start) if window else start
        w_end = min(window[1], horizon_end) if window else horizon_end
        exp_end = min(w_end, expected_through)
        act_end = min(w_end, eval_end)

        if is_total:
            goal_value = float(goal.target)
            actual = sum(v for d, v in day_actual.items() if d <= act_end)
            expected = sum(v for d, v in day_share.items() if d <= exp_end) if end is not None else None
        else:
            goal_value = sum(v for d, v in day_share.items() if w_start <= d <= w_end)
            actual = sum(v for d, v in day_actual.items() if w_start <= d <= act_end)
            expected = sum(v for d, v in day_share.items() if w_start <= d <= exp_end)

        # 4. Completion rate & streaks -----------------------------------------------------
        if is_total:
            units_source = [
                (d, day_actual.get(d, 0) > EPSILON, d <= expected_through)
                for d, t in sorted(day_types.items())
                if t == DayType.ACTIVE and d <= eval_end
            ]
            in_window = [(a, due) for d, a, due in units_source if w_start <= d <= act_end]
            streak_units = [StreakUnit(a, due) for d, a, due in units_source if d <= act_end]
        else:
            ordered = sorted(buckets.values(), key=lambda b: b.start)
            relevant = [b for b in ordered if b.target > EPSILON and b.days[0] <= eval_end]
            in_window = [(b.achieved, b.due) for b in relevant if w_start <= b.days[-1] and b.days[0] <= act_end]
            streak_units = [StreakUnit(b.achieved, b.due) for b in relevant if b.days[0] <= act_end]

        # Day shares are fractions: normalise float noise (e.g. 12.000000000000004).
        goal_value, actual = round(goal_value, 6), round(actual, 6)
        expected = round(expected, 6) if expected is not None else None

        completed_periods = sum(1 for achieved, due in in_window if achieved)
        due_periods = sum(1 for achieved, due in in_window if due or achieved)
        completion_rate = (completed_periods / due_periods * 100) if due_periods else None

        # 5. Status --------------------------------------------------------------------------
        ended_at = w_end if window else end
        ended = ended_at is not None and expected_through >= ended_at
        status = compute_status(
            not_started=as_of < start,
            paused=challenge.status == Challenge.Status.PAUSED,
            manually_completed=challenge.status == Challenge.Status.COMPLETED,
            ended=ended,
            actual=actual,
            goal=goal_value,
            expected=expected,
            goal_is_final=window is None and (end is not None or is_total),
        )

        # 6. Averages --------------------------------------------------------------------
        elapsed_active = sum(
            1
            for d, t in day_types.items()
            if t == DayType.ACTIVE and w_start <= d <= act_end and (d <= expected_through or day_actual.get(d, 0) > EPSILON)
        )
        average = actual / elapsed_active if elapsed_active else None

        # 7. Today -----------------------------------------------------------------------------
        today = self._today_info(goal, is_total, day_types, day_bucket, day_actual)

        # 8. Day series (calendar / heatmap / charts) --------------------------------------
        days: list[DayPoint] = []
        if include_series:
            for d in daterange(w_start, min(w_end, max(eval_end, w_start))):
                days.append(self._day_point(d, day_types, day_bucket, day_actual, day_share, is_total, as_of))

        progress = (actual / goal_value * 100) if goal_value > EPSILON else None
        result = ProgressResult(
            challenge_id=challenge.pk,
            goal_obj=goal,
            goal=goal_value,
            actual=actual,
            expected=expected,
            remaining=max(goal_value - actual, 0.0),
            progress=progress,
            gap=(actual - expected) if expected is not None else None,
            status=status,
            completion_rate=completion_rate,
            completed_periods=completed_periods,
            due_periods=due_periods,
            current_streak=current_streak(streak_units),
            best_streak=best_streak(streak_units),
            streak_unit=STREAK_UNITS[goal.period],
            average=average,
            period=goal.period,
            target=float(goal.target),
            window=(w_start, w_end),
            today=today,
            buckets=[b.as_dict() for b in sorted(buckets.values(), key=lambda b: b.start) if b.days[0] <= w_end and b.days[-1] >= w_start]
            if include_series
            else [],
        )
        result.days = days
        result.statistics = compute_statistics(
            day_types=day_types,
            day_actual=day_actual,
            day_entries=day_entries,
            day_share=day_share,
            day_bucket=day_bucket,
            is_daily=goal.period == Goal.Period.DAILY,
            start=w_start,
            end=act_end,
            expected_through=expected_through,
            goal=goal,
            week_start=self.week_start,
            detailed=include_series,
        )
        result.milestones = self._milestones(challenge, day_actual, goal)
        return result

    def _today_info(self, goal, is_total, day_types, day_bucket, day_actual) -> dict:
        as_of = self.as_of
        dtype = day_types.get(as_of, DayType.OUTSIDE)
        today_actual = day_actual.get(as_of, 0.0)
        info = {
            "date": as_of.isoformat(),
            "type": dtype.value,
            "actual": round(today_actual, 2),
            "target": None,
            "period_actual": None,
            "period_target": None,
            "remaining": None,
            "done": False,
            "status": "outside",
        }
        if is_total:
            info["done"] = today_actual > EPSILON
        else:
            bucket = day_bucket.get(as_of)
            if bucket is not None:
                info["period_actual"] = round(bucket.actual, 2)
                info["period_target"] = round(bucket.target, 2)
                info["remaining"] = round(max(bucket.target - bucket.actual, 0.0), 2)
                info["target"] = round(bucket.target, 2) if bucket.goal.period == Goal.Period.DAILY else info["remaining"]
                info["done"] = bucket.achieved
        if info["done"]:
            info["status"] = "done"
        elif dtype == DayType.ACTIVE:
            info["status"] = "partial" if today_actual > EPSILON else "pending"
        else:
            info["status"] = dtype.value
        info["display"] = {
            "actual": format_value(today_actual, goal),
            "target": format_value(info["target"], goal) if info["target"] is not None else None,
            "period_actual": format_value(info["period_actual"], goal) if info["period_actual"] is not None else None,
            "period_target": format_value(info["period_target"], goal) if info["period_target"] is not None else None,
        }
        return info

    def _day_point(self, d, day_types, day_bucket, day_actual, day_share, is_total, as_of) -> DayPoint:
        dtype = day_types.get(d, DayType.OUTSIDE)
        actual = day_actual.get(d, 0.0)
        share = day_share.get(d, 0.0)
        bucket = day_bucket.get(d)
        daily = bucket is not None and bucket.goal.period == Goal.Period.DAILY
        achieved = bucket.achieved if daily else actual > EPSILON
        if dtype == DayType.OUTSIDE:
            status = "outside"
        elif achieved:
            status = "done"
        elif dtype == DayType.PAUSED:
            status = "paused"
        elif dtype == DayType.REST:
            status = "rest"
        elif d > as_of:
            status = "future"
        elif d == as_of and not self.day_closed:
            status = "partial" if actual > EPSILON else "pending"
        elif actual > EPSILON:
            status = "partial"
        elif daily:
            status = "missed"
        else:
            status = "empty"
        return DayPoint(date=d, type=dtype, actual=actual, target=share, status=status)

    def _milestones(self, challenge, day_actual, goal) -> list[dict]:
        cache = getattr(challenge, "_prefetched_objects_cache", {})
        milestones = list(cache["milestones"]) if "milestones" in cache else list(challenge.milestones.all())
        if not milestones:
            return []
        cumulative, reached_on = 0.0, {}
        ordered = sorted(milestones, key=lambda m: m.target_value)
        for d in sorted(day_actual):
            cumulative += day_actual[d]
            for m in ordered:
                if m.pk not in reached_on and cumulative >= float(m.target_value) - EPSILON:
                    reached_on[m.pk] = d
        total = cumulative
        return [
            {
                "id": m.pk,
                "title": m.title,
                "target": float(m.target_value),
                "target_display": format_value(float(m.target_value), goal),
                "reached": m.pk in reached_on,
                "reached_on": reached_on[m.pk].isoformat() if m.pk in reached_on else None,
                "progress": round(min(total / float(m.target_value) * 100, 100), 1),
            }
            for m in ordered
        ]

    def _empty(self, challenge, start, ref_day) -> ProgressResult:
        return ProgressResult(
            challenge_id=challenge.pk, goal_obj=None, goal=0.0, actual=0.0, expected=None, remaining=0.0,
            progress=None, gap=None,
            status=ProgressStatus.NOT_STARTED if self.as_of < start else ProgressStatus.ON_TRACK,
            completion_rate=None, completed_periods=0, due_periods=0, current_streak=0, best_streak=0,
            streak_unit="day", average=None, period=None, target=None, window=(start, ref_day),
            today={"date": self.as_of.isoformat(), "type": "outside", "status": "outside", "done": False,
                   "actual": 0, "target": None, "display": {}},
        )
