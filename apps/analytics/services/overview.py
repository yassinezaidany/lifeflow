"""Cross-challenge analytics for a period (uses the ProgressEngine for every number)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from apps.challenges.models import Challenge
from apps.core.dates import user_today, week_start_for
from apps.planner import services as planner
from apps.planner.models import PlannedActivity
from apps.tracking.models import ChallengeEntry

from .progress import ProgressEngine

PERIODS = {"30d": 30, "90d": 90, "month": None, "year": 365}


def period_bounds(user, key: str) -> tuple[date, date]:
    today = user_today(user)
    if key == "month":
        return today.replace(day=1), today
    days = PERIODS.get(key) or 30
    return today - timedelta(days=days - 1), today


def build_overview(user, key: str = "30d") -> dict:
    start, end = period_bounds(user, key)
    challenges = list(ProgressEngine.prefetch(
        Challenge.objects.filter(user=user, start_date__lte=end).exclude(status=Challenge.Status.ARCHIVED)
    ))
    results = ProgressEngine(user).evaluate_many(challenges, include_series=True, window=(start, end))
    rows = [{"challenge": c, "progress": results[c.pk]} for c in challenges if results[c.pk].window[0] <= end]
    rows.sort(key=lambda r: -(r["progress"].completion_rate or 0))

    planner.ensure_occurrences(user, start, end)
    acts = list(PlannedActivity.objects.filter(user=user, date__range=(start, end)).select_related("category"))
    profile = user.profile
    weeks: dict[date, list] = defaultdict(list)
    by_category: dict[str, dict] = {}
    for a in acts:
        weeks[week_start_for(a.date, profile.week_start)].append(a)
        if a.status in (PlannedActivity.Status.CANCELLED, PlannedActivity.Status.RESCHEDULED):
            continue
        name = a.category.name if a.category else "—"
        color = a.effective_color
        bucket = by_category.setdefault(name, {"name": name, "color": color, "minutes": 0, "done": 0})
        bucket["minutes"] += a.duration_minutes
        if a.is_done:
            bucket["done"] += a.actual_minutes or a.duration_minutes
    planner_weeks = [{"start": k.isoformat(), **planner.summarize(v, user)} for k, v in sorted(weeks.items())]

    weekday_counts = [0] * 7
    for d in ChallengeEntry.objects.filter(user=user, date__range=(start, end)).values_list("date", flat=True):
        weekday_counts[d.weekday()] += 1

    rates = [r["progress"].completion_rate for r in rows if r["progress"].completion_rate is not None]
    return {
        "key": key, "start": start, "end": end, "rows": rows,
        "avg_completion": round(sum(rates) / len(rates), 1) if rates else None,
        "planner": planner.summarize(acts, user),
        "planner_weeks": planner_weeks,
        "categories": sorted(by_category.values(), key=lambda c: -c["minutes"])[:8],
        "weekday_counts": weekday_counts,
        "entries": sum(weekday_counts),
    }
