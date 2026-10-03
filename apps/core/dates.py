"""Date helpers. All "day" semantics in LifeFlow are evaluated in the user's timezone."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone


def user_tz(user) -> ZoneInfo:
    name = None
    profile = getattr(user, "profile", None) if user is not None and getattr(user, "is_authenticated", False) else None
    if profile is not None:
        name = profile.timezone
    try:
        return ZoneInfo(name or settings.DEFAULT_USER_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def user_now(user) -> datetime:
    return timezone.now().astimezone(user_tz(user))


def user_today(user) -> date:
    return user_now(user).date()


def daterange(start: date, end: date) -> Iterator[date]:
    """Inclusive range of dates."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def week_start_for(day: date, week_starts_on: int = 0) -> date:
    """`week_starts_on`: 0 = Monday ... 6 = Sunday."""
    offset = (day.weekday() - week_starts_on) % 7
    return day - timedelta(days=offset)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def parse_date(value, default: date | None = None) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return default
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return default


def minutes_between(start, end) -> int:
    """Minutes between two `time`s on the same day. 00:00 as end means midnight."""
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    if e == 0:
        e = 24 * 60
    return max(e - s, 0)


def format_minutes(total: float | int | None) -> str:
    if total is None:
        return "—"
    total = int(round(total))
    hours, minutes = divmod(total, 60)
    if hours and minutes:
        return f"{hours}h{minutes:02d}"
    if hours:
        return f"{hours}h"
    return f"{minutes}min"
