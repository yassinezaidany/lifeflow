"""Health check of a LifeFlow installation.

    python manage.py doctor          # human-readable report, exit code 1 if something is broken

Checks the database, migrations, secrets, static assets, fonts, translations, e-mail,
Web Push, AI assistant and the reminder scheduler.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"


class Command(BaseCommand):
    help = "Diagnose the LifeFlow installation."

    def handle(self, *args, **options):
        self.results: list[tuple[str, str, str]] = []
        for check in (self.check_database, self.check_migrations, self.check_secret, self.check_mode, self.check_static,
                      self.check_fonts, self.check_translations, self.check_media, self.check_email, self.check_push, self.check_assistant,
                      self.check_scheduler, self.check_data):
            try:
                check()
            except Exception as exc:  # a broken check must not hide the others
                self.add(FAIL, check.__name__.replace("check_", ""), str(exc))

        symbols = {OK: self.style.SUCCESS("✓"), WARN: self.style.WARNING("!"), FAIL: self.style.ERROR("✗"), INFO: "·"}
        self.stdout.write(self.style.MIGRATE_HEADING("LifeFlow — installation check"))
        for status, name, message in self.results:
            self.stdout.write(f" {symbols[status]} {name:<14} {message}")
        failures = sum(1 for s, _n, _m in self.results if s == FAIL)
        warnings = sum(1 for s, _n, _m in self.results if s == WARN)
        summary = f"{failures} problem(s), {warnings} warning(s)"
        self.stdout.write(self.style.ERROR(summary) if failures else (self.style.WARNING(summary) if warnings else self.style.SUCCESS("Everything looks good.")))
        if failures:
            sys.exit(1)

    def add(self, status, name, message):
        self.results.append((status, name, message))

    # ------------------------------------------------------------------ checks
    def check_database(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT sqlite_version()" if connection.vendor == "sqlite" else "SELECT VERSION()")
            version = cursor.fetchone()[0]
        self.add(OK, "database", f"{connection.vendor} {version} — {settings.DATABASES['default']['NAME']}")

    def check_migrations(self):
        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if pending:
            self.add(FAIL, "migrations", f"{len(pending)} pending — run `python manage.py migrate`")
        else:
            self.add(OK, "migrations", "up to date")

    def check_secret(self):
        key = settings.SECRET_KEY or ""
        if len(key) < 40 or "change-me" in key:
            self.add(FAIL if not settings.DEBUG else WARN, "secret key", "too short or default — set a long random SECRET_KEY in .env")
        else:
            self.add(OK, "secret key", "set")

    def check_mode(self):
        module = settings.SETTINGS_MODULE
        if settings.DEBUG:
            self.add(INFO, "mode", f"development ({module}, DEBUG=True)")
        else:
            https = getattr(settings, "USE_HTTPS", True)
            self.add(OK, "mode", f"production ({module}), HTTPS {'required' if https else 'disabled (local use)'}")
            if not settings.ALLOWED_HOSTS:
                self.add(FAIL, "hosts", "ALLOWED_HOSTS is empty")

    def check_static(self):
        css = settings.BASE_DIR / "static" / "css" / "app.css"
        if not css.exists():
            self.add(FAIL, "static", "static/css/app.css missing — run `npm run build`")
            return
        if not settings.DEBUG:
            manifest = Path(settings.STATIC_ROOT) / "staticfiles.json"
            if not manifest.exists():
                self.add(FAIL, "static", "not collected — run `python manage.py collectstatic --noinput`")
                return
        self.add(OK, "static", "built" + ("" if settings.DEBUG else " and collected"))

    def check_fonts(self):
        fonts = settings.BASE_DIR / "apps" / "reports" / "fonts"
        missing = [f for f in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf") if not (fonts / f).exists()]
        self.add(WARN if missing else OK, "pdf fonts", f"missing {', '.join(missing)} (Arabic PDFs degraded)" if missing else "DejaVu Sans embedded")

    def check_translations(self):
        compiled = []
        for code, _name in settings.LANGUAGES:
            if code == settings.LANGUAGE_CODE:
                continue
            mo = Path(settings.LOCALE_PATHS[0]) / code / "LC_MESSAGES" / "django.mo"
            if not mo.exists():
                self.add(WARN, "translations", f"{code} not compiled — run `python manage.py i18n compile`")
                return
            compiled.append(code)
        self.add(OK, "translations", ", ".join(["en (source)", *compiled]))

    def check_email(self):
        backend = settings.EMAIL_BACKEND.split(".")[-2]
        if "console" in settings.EMAIL_BACKEND or "locmem" in settings.EMAIL_BACKEND:
            self.add(INFO if settings.DEBUG else WARN, "e-mail", f"{backend}: e-mails are not really sent (password reset links appear in the console)")
        elif settings.EMAIL_BACKEND.endswith("BrevoEmailBackend"):
            if settings.BREVO_API_KEY:
                self.add(OK, "e-mail", f"Brevo HTTPS API, sender {settings.DEFAULT_FROM_EMAIL}")
            else:
                self.add(WARN, "e-mail", "Brevo backend selected but BREVO_API_KEY is empty — e-mails are not sent")
        else:
            self.add(OK, "e-mail", f"{backend} via {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")

    def check_media(self):
        if settings.MEDIA_IN_DATABASE:
            self.add(OK, "uploads", "stored in the database (MEDIA_STORAGE=db)")
        else:
            self.add(OK, "uploads", f"stored on disk in {settings.MEDIA_ROOT}")

    def check_push(self):
        if settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY:
            self.add(OK, "web push", "VAPID keys configured")
        else:
            self.add(INFO, "web push", "disabled — `python manage.py generate_vapid_keys --write` to enable")

    def check_assistant(self):
        if settings.ANTHROPIC_API_KEY:
            self.add(OK, "ai assistant", f"Claude ({settings.ASSISTANT_MODEL})")
        else:
            self.add(INFO, "ai assistant", "built-in parser (set ANTHROPIC_API_KEY to use Claude)")

    def check_scheduler(self):
        from apps.notifications.reminders import HEARTBEAT

        path = settings.LOG_DIR / HEARTBEAT
        via = " or call /internal/cron/reminders/ from an external cron" if settings.CRON_TOKEN else ""
        if not path.exists():
            self.add(WARN, "reminders", f"scheduler never ran — start `python manage.py run_scheduler`{via}")
            return
        last = datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
        age = timezone.now() - last
        if age > timedelta(minutes=30):
            self.add(WARN, "reminders", f"last run {int(age.total_seconds() // 60)} min ago — is the scheduler running?")
        else:
            self.add(OK, "reminders", f"last run {int(age.total_seconds() // 60)} min ago")

    def check_data(self):
        from apps.challenges.models import ChallengeTemplate

        User = get_user_model()
        templates = ChallengeTemplate.objects.filter(owner__isnull=True).count()
        self.add(OK if templates else WARN, "templates", f"{templates} built-in challenge templates" + ("" if templates else " — run `python manage.py seed_templates`"))
        users = User.objects.filter(is_demo=False).count()
        admins = User.objects.filter(is_superuser=True).count()
        self.add(INFO, "accounts", f"{users} user(s), {admins} administrator(s)" + ("" if admins else " — `python manage.py createsuperuser` for /admin/"))
