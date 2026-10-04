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
    """Duration of a time range. An end earlier than (or equal to) the start wraps to
    the next day: 23:00 → 07:00 = 480, 09:00 → 00:00 = 900, 00:00 → 00:00 = 1440."""
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    if e <= s:
        e += 24 * 60
    return e - s


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
