"""iCalendar (RFC 5545) export of planned activities."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone

from apps.core.dates import user_tz

from . import services
from .models import PlannedActivity

STATUS = {
    PlannedActivity.Status.CANCELLED: "CANCELLED",
    PlannedActivity.Status.COMPLETED: "CONFIRMED",
    PlannedActivity.Status.PARTIALLY_COMPLETED: "CONFIRMED",
}


def _escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Fold content lines at 75 octets (continuation lines start with a space)."""
    out, current = [], b""
    for ch in line:
        encoded = ch.encode("utf-8")
        if len(current) + len(encoded) > 75:
            out.append(current.decode("utf-8"))
            current = b" " + encoded
        else:
            current += encoded
    out.append(current.decode("utf-8"))
    return "\r\n".join(out)


def _utc(dt: datetime) -> str:
    return dt.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(user, start, end, name: str = "LifeFlow") -> str:
    services.ensure_occurrences(user, start, end)
    tz = user_tz(user)
    activities = (
        PlannedActivity.objects.filter(user=user, date__range=(start, end))
        .exclude(status=PlannedActivity.Status.RESCHEDULED)
        .select_related("category", "challenge")
    )
    host = settings.SITE_URL.split("//")[-1].split("/")[0] or "lifeflow"
    stamp = _utc(timezone.now())
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//LifeFlow//Planner//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}", f"X-WR-TIMEZONE:{tz.key}", "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
    ]
    for a in activities:
        begin = datetime.combine(a.date, a.start_time, tzinfo=tz)
        finish = begin + timedelta(minutes=a.duration_minutes)
        description = "\n".join(filter(None, [
            a.description, a.notes,
            f"Challenge: {a.challenge.name}" if a.challenge else "",
            f"Status: {a.get_status_display()}",
        ]))
        lines += [
            "BEGIN:VEVENT",
            f"UID:activity-{a.pk}@{host}",
            f"DTSTAMP:{stamp}",
            f"LAST-MODIFIED:{_utc(a.updated_at)}",
            f"DTSTART:{_utc(begin)}",
            f"DTEND:{_utc(finish)}",
            f"SUMMARY:{_escape(('✓ ' if a.is_done else '') + a.title)}",
            f"DESCRIPTION:{_escape(description)}",
            f"STATUS:{STATUS.get(a.status, 'TENTATIVE' if a.status == PlannedActivity.Status.PLANNED else 'CONFIRMED')}",
        ]
        if a.category:
            lines.append(f"CATEGORIES:{_escape(a.category.name)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
