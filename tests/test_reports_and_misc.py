from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.dates import user_today
from apps.core.models import AuditLog
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.reports.generators.pdf import render_monthly_report_pdf
from apps.reports.models import MonthlyReport
from apps.reports.services.monthly import generate_monthly_report
from apps.tracking.models import ChallengeEntry

from .factories import add_entry, make_challenge, make_user

pytestmark = pytest.mark.django_db


class TestReports:
    def test_snapshot_is_immutable(self, user):
        c = make_challenge(user, start=date(2025, 1, 1), end=date(2025, 3, 31))
        for d in range(1, 11):
            add_entry(c, date(2025, 1, d), amount=2)
        report = generate_monthly_report(user, 2025, 1)
        snap = report.challenges.get()
        assert (snap.goal, snap.actual, snap.status) == (62, 20, "missed")
        assert len(snap.daily_series) == 31
        # Later changes don't alter the old report
        ChallengeEntry.objects.filter(challenge=c).delete()
        c.name = "Renamed"
        c.save()
        snap.refresh_from_db()
        assert snap.actual == 20 and snap.name == "Challenge"
        c.delete()
        snap.refresh_from_db()
        assert snap.challenge_id is None and snap.actual == 20

    def test_regenerate_creates_new_version(self, user):
        make_challenge(user, start=date(2025, 1, 1))
        r1 = generate_monthly_report(user, 2025, 1)
        r2 = generate_monthly_report(user, 2025, 1)
        assert (r1.version, r2.version) == (1, 2)
        assert MonthlyReport.objects.filter(user=user).count() == 2

    def test_future_month_rejected(self, api, user):
        nxt = user_today(user) + timedelta(days=40)
        r = api.post("/api/reports/monthly/", {"year": nxt.year, "month": nxt.month}, format="json")
        assert r.status_code == 400

    def test_partial_current_month(self, api, user):
        make_challenge(user, start=user_today(user) - timedelta(days=40))
        r = api.post("/api/reports/monthly/", {}, format="json")
        assert r.status_code == 201 and r.json()["summary"]["is_partial"] is True

    def test_pdf_and_planner_section(self, user):
        c = make_challenge(user, start=date(2025, 1, 1),
                           fields=[{"label": "Duration", "key": "d", "field_type": "duration"}],
                           goal={"metric": "d", "period": "weekly", "aggregation": "sum", "target": 300})
        add_entry(c, date(2025, 1, 6), d=120)
        report = generate_monthly_report(user, 2025, 1)
        pdf = render_monthly_report_pdf(report)
        assert pdf[:4] == b"%PDF" and len(pdf) > 2000

    def test_web_generate(self, web, user):
        make_challenge(user, start=date(2025, 1, 1))
        r = web.post(reverse("reports:generate"), {"month": "2025-01"})
        assert r.status_code == 302 and MonthlyReport.objects.filter(user=user).exists()
        assert web.post(reverse("reports:generate"), {"month": "garbage"}).status_code == 302
        assert Notification.objects.filter(user=user, kind="report_ready").exists()

    def test_report_without_challenges(self, user):
        report = generate_monthly_report(user, 2025, 1)
        assert report.summary["challenges"] == 0
        assert render_monthly_report_pdf(report)[:4] == b"%PDF"


class TestTimezone:
    def test_user_today_follows_profile_timezone(self):
        fixed = datetime(2026, 3, 1, 23, 30, tzinfo=dt_timezone.utc)
        tokyo = make_user("tokyo", tz="Asia/Tokyo")
        la = make_user("la", tz="America/Los_Angeles")
        with mock.patch("django.utils.timezone.now", return_value=fixed):
            assert user_today(tokyo) == date(2026, 3, 2)
            assert user_today(la) == date(2026, 3, 1)

    def test_entry_future_check_uses_user_timezone(self):
        fixed = datetime(2026, 3, 1, 23, 30, tzinfo=dt_timezone.utc)
        tokyo = make_user("tokyo2", tz="Asia/Tokyo")
        c = make_challenge(tokyo, start=date(2026, 2, 1))
        from apps.tracking.services import create_entry
        with mock.patch("django.utils.timezone.now", return_value=fixed):
            entry = create_entry(tokyo, c, date(2026, 3, 2), {"amount": 2})  # already March 2nd in Tokyo
        assert entry.pk


class TestMisc:
    def test_audit_trail(self, api, user):
        r = api.post("/api/challenges/", {"name": "A", "start_date": "2026-01-01", "fields": [],
                                          "goal": {"metric": None, "period": "daily", "target": 1}}, format="json")
        api.patch(f"/api/challenges/{r.json()['id']}/", {"name": "B"}, format="json")
        actions = set(AuditLog.objects.filter(user=user).values_list("action", flat=True))
        assert {"challenge_created", "challenge_updated"} <= actions

    def test_notifications_respect_preferences_and_dedupe(self, user, api):
        assert notify(user, "system", "Hello", dedupe_key="k1")
        assert notify(user, "system", "Hello", dedupe_key="k1") is None
        user.settings.notifications_enabled = False
        user.settings.save()
        assert notify(user, "system", "Muted") is None
        r = api.post("/api/notifications/read-all/")
        assert r.json()["updated"] == 1

    def test_send_reminders_command(self, user):
        from django.core.management import call_command
        call_command("send_reminders", verbosity=0)

    def test_dashboard_and_calendar_api(self, api, user):
        make_challenge(user, start=user_today(user) - timedelta(days=3))
        r = api.get("/api/dashboard/")
        assert r.status_code == 200 and len(r.json()["challenges"]) == 1 and len(r.json()["last7"]) == 7
        r = api.get("/api/calendar/", {"month": "2026-02"})
        assert r.status_code == 200 and len(r.json()["weeks"]) >= 4
        assert api.get("/api/calendar/", {"month": "bad"}).status_code == 200
        assert api.get("/api/calendar/day/", {"date": "2026-02-10"}).status_code == 200

    def test_journal_and_review_api(self, api, user):
        r = api.post("/api/journal/", {"date": "2026-01-01", "content": "Hello", "mood": 4}, format="json")
        assert r.status_code == 201
        assert api.post("/api/journal/", {"date": "2026-01-01", "content": "  "}, format="json").status_code == 400
        assert api.post("/api/journal/", {"date": "2026-01-01", "content": "x", "mood": 9}, format="json").status_code == 400
        r = api.post("/api/journal/weekly-reviews/", {"week_start": "2026-01-07", "went_well": "ok"}, format="json")
        assert r.status_code == 201 and r.json()["week_start"] == "2026-01-05"
        r = api.post("/api/journal/weekly-reviews/", {"week_start": "2026-01-06", "improve": "more"}, format="json")
        assert r.json()["id"] is not None
        assert api.get("/api/journal/weekly-reviews/").json()["count"] == 1

    def test_security_headers(self, web):
        r = web.get(reverse("dashboard:home"))
        assert "frame-ancestors 'none'" in r["Content-Security-Policy"]
        assert r["X-Frame-Options"] == "DENY"
        assert r["X-Content-Type-Options"] == "nosniff"

    def test_friendly_api_errors(self, api):
        r = api.get("/api/challenges/999999/")
        assert r.status_code == 404 and r.json() == {"detail": "Not found."}

    def test_csv_formula_injection_neutralised(self, web, user):
        c = make_challenge(user, start=date(2025, 1, 1))
        e = add_entry(c, date(2025, 1, 2), amount=1)
        e.note = "=HYPERLINK(\"http://x\")"
        e.save()
        content = web.get(reverse("reports:export") + "?format=csv&kind=entries").content.decode("utf-8-sig")
        assert "'=HYPERLINK" in content

    def test_xss_escaped_in_templates(self, web, user):
        make_challenge(user, name="<script>alert(1)</script>", start=date(2025, 1, 1))
        content = web.get(reverse("challenges:list")).content
        assert b"<script>alert(1)</script>" not in content
        assert b"&lt;script&gt;" in content
