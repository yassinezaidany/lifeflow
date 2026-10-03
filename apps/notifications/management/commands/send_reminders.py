"""Generate due reminders. Run periodically (e.g. every 10 minutes via cron / Task Scheduler):

    python manage.py send_reminders

Idempotent thanks to per-notification dedupe keys.
"""
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from apps.core.dates import user_now
from apps.dashboard.services import challenge_cards, today_activities
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.planner.models import PlannedActivity

REMINDER_LEAD = timedelta(minutes=15)


class Command(BaseCommand):
    help = "Create in-app reminders (activities, end of day, weekly review)."

    def handle(self, *args, **options):
        users = get_user_model().objects.filter(is_active=True, settings__notifications_enabled=True).select_related("profile", "settings")
        created = 0
        for user in users:
            created += self._for_user(user)
        self.stdout.write(self.style.SUCCESS(f"{created} notification(s) created"))

    def _for_user(self, user) -> int:
        now = user_now(user)
        naive_now = now.replace(tzinfo=None)
        prefs = user.settings
        count = 0
        if prefs.notify_activity_reminders:
            for a in today_activities(user, now.date()):
                if a.status != PlannedActivity.Status.PLANNED:
                    continue
                start = datetime.combine(a.date, a.start_time)
                if naive_now <= start <= naive_now + REMINDER_LEAD:
                    if notify(user, Notification.Kind.ACTIVITY_REMINDER, _("Coming up: %(t)s") % {"t": a.title},
                              body=f"{a.start_time:%H:%M} – {a.end_time:%H:%M}", url="/today/",
                              dedupe_key=f"act:{a.pk}:{a.date}", setting="notify_activity_reminders"):
                        count += 1
        if prefs.notify_end_of_day and now.time() >= prefs.end_of_day_time:
            pending = [c for c in challenge_cards(user) if c["progress"].today.get("status") in ("pending", "partial")]
            if pending:
                names = ", ".join(c["challenge"].name for c in pending[:3])
                if notify(user, Notification.Kind.END_OF_DAY, _("%(n)s challenge(s) still open today") % {"n": len(pending)},
                          body=names, url="/today/", dedupe_key=f"eod:{now.date()}", setting="notify_end_of_day"):
                    count += 1
        week_last_day = (user.profile.week_start + 6) % 7
        if prefs.notify_weekly_review and now.weekday() == week_last_day and now.hour >= 18:
            if notify(user, Notification.Kind.WEEKLY_REVIEW, _("Time for your weekly review"),
                      body=_("Take two minutes to reflect on your week."), url="/journal/review/",
                      dedupe_key=f"review:{now.date()}", setting="notify_weekly_review"):
                count += 1
        return count
