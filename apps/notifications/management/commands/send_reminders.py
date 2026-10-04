"""Generate due reminders once. Schedule it every 5–10 minutes (cron / Windows Task Scheduler),
or use `python manage.py run_scheduler` which loops for you.

    python manage.py send_reminders
"""
from django.core.management.base import BaseCommand

from apps.notifications.reminders import run_all


class Command(BaseCommand):
    help = "Create due reminders (activities, morning summary, challenge reminders, end of day, weekly review)."

    def handle(self, *args, **options):
        created = run_all()
        self.stdout.write(self.style.SUCCESS(f"{created} notification(s) created"))
