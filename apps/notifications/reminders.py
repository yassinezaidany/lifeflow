"""Reminder rules, evaluated in each user's timezone. Idempotent (dedupe keys), so the
runner can be called as often as wanted (every 5–10 minutes is ideal)."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.core.dates import user_now
from apps.planner.models import PlannedActivity

from .models import Notification
from .services import notify

ACTIVITY_LEAD = timedelta(minutes=15)
WINDOW = timedelta(minutes=90)  # a time-based reminder is sent at most this late (e.g. server was down)


def _due(now: datetime, at: time) -> bool:
    start = datetime.combine(now.date(), at)
    naive = now.replace(tzinfo=None)
    return start <= naive < start + WINDOW


def run_for_user(user, now: datetime | None = None) -> int:
    from apps.dashboard.services import challenge_cards, today_activities  # local import: avoids app-loading cycles

    now = now or user_now(user)
    prefs = user.settings
    if not prefs.notifications_enabled:
        return 0
    language = getattr(user.profile, "language", "en") or "en"
    sent = 0
    with translation.override(language):
        today = now.date()
        naive = now.replace(tzinfo=None)
        activities = None
        cards = None

        if prefs.notify_activity_reminders:
            activities = today_activities(user, today)
            for a in activities:
                if a.status != PlannedActivity.Status.PLANNED:
                    continue
                start = datetime.combine(a.date, a.start_time)
                if naive <= start <= naive + ACTIVITY_LEAD:
                    if notify(user, Notification.Kind.ACTIVITY_REMINDER, _("Coming up: %(t)s") % {"t": a.title},
                              body=f"{a.start_time:%H:%M} – {a.end_time:%H:%M}", url="/today/",
                              dedupe_key=f"act:{a.pk}:{a.date}", setting="notify_activity_reminders"):
                        sent += 1

        if prefs.notify_daily_goals and _due(now, prefs.morning_summary_time):
            activities = activities if activities is not None else today_activities(user, today)
            cards = challenge_cards(user)
            todo = [c for c in cards if c["progress"].today.get("status") in ("pending", "partial")]
            planned = [a for a in activities if a.status == PlannedActivity.Status.PLANNED]
            if todo or planned:
                parts = []
                if todo:
                    parts.append(ngettext("%(n)s challenge to do", "%(n)s challenges to do", len(todo)) % {"n": len(todo)})
                if planned:
                    parts.append(ngettext("%(n)s activity planned", "%(n)s activities planned", len(planned)) % {"n": len(planned)})
                body = " · ".join(parts)
                if todo:
                    body += " — " + ", ".join(c["challenge"].name for c in todo[:4])
                if notify(user, Notification.Kind.DAILY_GOAL, _("Your day at a glance"), body=body, url="/today/",
                          dedupe_key=f"morning:{today}", setting="notify_daily_goals"):
                    sent += 1

        reminders = [c for c in user.challenges.filter(status="active", reminder_time__isnull=False) if _due(now, c.reminder_time)]
        if reminders:
            cards = cards if cards is not None else challenge_cards(user)
            by_id = {c["challenge"].pk: c["progress"] for c in cards}
            for challenge in reminders:
                progress = by_id.get(challenge.pk)
                if progress is None or progress.today.get("status") not in ("pending", "partial"):
                    continue  # rest day, done, paused or not started
                if notify(user, Notification.Kind.CHALLENGE_REMINDER, _("Time for %(name)s") % {"name": challenge.name},
                          body=progress.goal_description, url=f"/challenges/{challenge.pk}/",
                          dedupe_key=f"challenge:{challenge.pk}:{today}", setting="notify_daily_goals"):
                    sent += 1

        if prefs.notify_end_of_day and now.time() >= prefs.end_of_day_time:
            cards = cards if cards is not None else challenge_cards(user)
            pending = [c for c in cards if c["progress"].today.get("status") in ("pending", "partial")]
            if pending:
                names = ", ".join(c["challenge"].name for c in pending[:3])
                if notify(user, Notification.Kind.END_OF_DAY,
                          ngettext("%(n)s challenge still open today", "%(n)s challenges still open today", len(pending)) % {"n": len(pending)},
                          body=names, url="/today/", dedupe_key=f"eod:{today}", setting="notify_end_of_day"):
                    sent += 1

        week_last_day = (user.profile.week_start + 6) % 7
        if prefs.notify_weekly_review and now.weekday() == week_last_day and now.hour >= 18:
            if notify(user, Notification.Kind.WEEKLY_REVIEW, _("Time for your weekly review"),
                      body=_("Take two minutes to reflect on your week."), url="/journal/review/",
                      dedupe_key=f"review:{today}", setting="notify_weekly_review"):
                sent += 1
    return sent


def run_all() -> int:
    users = get_user_model().objects.filter(is_active=True, settings__notifications_enabled=True).select_related("profile", "settings")
    return sum(run_for_user(u) for u in users)
