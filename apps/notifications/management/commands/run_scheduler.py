"""Tiny built-in scheduler: runs the reminder engine every N seconds (default 300).

    python manage.py run_scheduler            # keep it running next to the web server
    python manage.py run_scheduler --once     # single pass (same as send_reminders)

For production, prefer cron / systemd timers / Windows Task Scheduler calling send_reminders.
"""
import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.notifications.reminders import run_all

logger = logging.getLogger("lifeflow")


class Command(BaseCommand):
    help = "Run reminders periodically."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=300, help="Seconds between runs (min 60).")
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **opts):
        interval = max(opts["interval"], 60)
        self.stdout.write(f"LifeFlow scheduler started (every {interval}s). Ctrl+C to stop.")
        while True:
            close_old_connections()
            try:
                n = run_all()
                if n:
                    self.stdout.write(f"{n} notification(s) sent")
            except Exception:  # keep the loop alive
                logger.exception("Scheduler run failed")
            if opts["once"]:
                return
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write("Scheduler stopped.")
                return
