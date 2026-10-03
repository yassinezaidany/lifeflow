"""Descriptive statistics derived from the engine's per-day data (no extra queries)."""
from __future__ import annotations

from collections import OrderedDict
from datetime import date

from apps.core.dates import daterange, week_start_for

from .goals import EPSILON, format_value
from .schedules import DayType


def compute_statistics(
    *,
    day_types: dict,
    day_actual: dict,
    day_entries: dict,
    day_share: dict,
    day_bucket: dict,
    is_daily: bool,
    start: date,
    end: date,
    expected_through: date,
    goal,
    week_start: int,
    detailed: bool,
) -> dict:
    fmt = lambda v: format_value(v, goal)  # noqa: E731
    if end < start:
        return {"total": 0, "entries": 0, "active_days": 0, "display": {}}

    days = list(daterange(start, end))
    with_entries = [d for d in days if day_entries.get(d)]
    values = [day_actual.get(d, 0.0) for d in with_entries]
    eligible_elapsed = [d for d in days if day_types.get(d) == DayType.ACTIVE and d <= expected_through]

    def achieved(d: date) -> bool:
        bucket = day_bucket.get(d)
        if is_daily and bucket is not None:
            return bucket.achieved
        return day_actual.get(d, 0.0) > EPSILON

    total = sum(day_actual.get(d, 0.0) for d in days)
    entries = sum(day_entries.get(d, 0) for d in days)
    completed_days = sum(1 for d in days if achieved(d))
    missed_days = sum(1 for d in eligible_elapsed if not achieved(d)) if is_daily else None

    best_day = max(with_entries, key=lambda d: day_actual.get(d, 0.0)) if with_entries else None
    worst_pool = eligible_elapsed or with_entries
    worst_day = min(worst_pool, key=lambda d: day_actual.get(d, 0.0)) if worst_pool else None

    stats = {
        "total": round(total, 2),
        "entries": entries,
        "active_days": len(with_entries),
        "scheduled_days": len(eligible_elapsed),
        "completed_days": completed_days,
        "missed_days": missed_days,
        "rest_days": sum(1 for d in days if day_types.get(d) == DayType.REST),
        "paused_days": sum(1 for d in days if day_types.get(d) == DayType.PAUSED),
        "average_per_entry": round(total / entries, 2) if entries else None,
        "average_per_active_day": round(total / len(eligible_elapsed), 2) if eligible_elapsed else None,
        "min": round(min(values), 2) if values else None,
        "max": round(max(values), 2) if values else None,
        "best_day": {"date": best_day.isoformat(), "value": round(day_actual[best_day], 2)} if best_day else None,
        "worst_day": {"date": worst_day.isoformat(), "value": round(day_actual.get(worst_day, 0.0), 2)} if worst_day else None,
    }
    stats["display"] = {
        "total": fmt(stats["total"]),
        "average_per_entry": fmt(stats["average_per_entry"]),
        "average_per_active_day": fmt(stats["average_per_active_day"]),
        "min": fmt(stats["min"]),
        "max": fmt(stats["max"]),
        "best_day": fmt(stats["best_day"]["value"]) if best_day else "—",
        "worst_day": fmt(stats["worst_day"]["value"]) if worst_day else "—",
    }

    if detailed:
        weekly: OrderedDict[date, dict] = OrderedDict()
        monthly: OrderedDict[str, dict] = OrderedDict()
        for d in days:
            wk = week_start_for(d, week_start)
            mk = d.strftime("%Y-%m")
            for bucket, key in ((weekly, wk), (monthly, mk)):
                row = bucket.setdefault(key, {"actual": 0.0, "target": 0.0})
                row["actual"] += day_actual.get(d, 0.0)
                row["target"] += day_share.get(d, 0.0)
        stats["weekly"] = [
            {"start": k.isoformat(), "actual": round(v["actual"], 2), "target": round(v["target"], 2)} for k, v in weekly.items()
        ]
        stats["monthly"] = [
            {"month": k, "actual": round(v["actual"], 2), "target": round(v["target"], 2)} for k, v in monthly.items()
        ]
    return stats
