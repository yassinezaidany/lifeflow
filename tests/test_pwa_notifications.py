from datetime import date, datetime, time, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.urls import reverse

from apps.notifications import reminders
from apps.notifications.models import Notification, PushSubscription
from apps.notifications.services import notify
from apps.planner.models import PlannedActivity

from .factories import add_entry, make_challenge

pytestmark = pytest.mark.django_db
SUB = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc123", "keys": {"p256dh": "BPkey", "auth": "authkey"}}


class TestPWA:
    def test_service_worker_served_at_root(self, client):
        r = client.get("/sw.js")
        assert r.status_code == 200
        assert r["Content-Type"].startswith("application/javascript")
        assert r["Service-Worker-Allowed"] == "/"
        body = r.content.decode()
        assert "lf-shell-" in body and "/static/css/app.css" in body and "/offline/" in body
        assert "addEventListener(\"push\"" in body

    def test_manifest(self, client):
        data = client.get("/manifest.webmanifest").json()
        assert data["display"] == "standalone" and data["start_url"].startswith("/today/")
        assert {i["purpose"] for i in data["icons"]} == {"any", "maskable"}

    def test_offline_page_public(self, client):
        assert client.get("/offline/").status_code == 200

    def test_signed_out_page_clears_cached_user_data(self, client):
        assert b"clear-user-data" in client.get(reverse("accounts:login")).content


class TestPush:
    def test_key_endpoint_reports_disabled(self, api):
        assert api.get("/api/notifications/push/key/").json()["enabled"] is False
        assert api.post("/api/notifications/push/subscribe/", SUB, format="json").status_code == 400

    def test_subscribe_send_and_cleanup(self, api, user, settings):
        settings.VAPID_PUBLIC_KEY, settings.VAPID_PRIVATE_KEY = "pub", "priv"
        assert api.get("/api/notifications/push/key/").json() == {"enabled": True, "public_key": "pub", "devices": 0}
        assert api.post("/api/notifications/push/subscribe/", SUB, format="json").status_code == 201
        assert api.post("/api/notifications/push/subscribe/", SUB, format="json").status_code == 201  # idempotent
        assert PushSubscription.objects.filter(user=user).count() == 1
        with mock.patch("pywebpush.webpush") as wp:
            notify(user, "system", "Hello", body="World", url="/today/")
            assert wp.call_count == 1
            assert '"title": "Hello"' in wp.call_args.kwargs["data"]
        # expired subscription → removed
        from pywebpush import WebPushException
        gone = WebPushException("gone", response=mock.Mock(status_code=410))
        with mock.patch("pywebpush.webpush", side_effect=gone):
            notify(user, "system", "Again")
        assert not PushSubscription.objects.filter(user=user).exists()

    def test_push_respects_preference(self, api, user, settings):
        settings.VAPID_PUBLIC_KEY, settings.VAPID_PRIVATE_KEY = "pub", "priv"
        api.post("/api/notifications/push/subscribe/", SUB, format="json")
        user.settings.push_notifications = False
        user.settings.save()
        with mock.patch("pywebpush.webpush") as wp:
            notify(user, "system", "Quiet")
        assert wp.call_count == 0 and Notification.objects.filter(title="Quiet").exists()

    def test_subscription_validation_and_unsubscribe(self, api, settings):
        settings.VAPID_PUBLIC_KEY, settings.VAPID_PRIVATE_KEY = "pub", "priv"
        assert api.post("/api/notifications/push/subscribe/", {**SUB, "endpoint": "http://insecure.example"}, format="json").status_code == 400
        assert api.post("/api/notifications/push/subscribe/", {**SUB, "keys": {}}, format="json").status_code == 400
        api.post("/api/notifications/push/subscribe/", SUB, format="json")
        assert api.post("/api/notifications/push/unsubscribe/", {"endpoint": SUB["endpoint"]}, format="json").json()["unsubscribed"]

    def test_device_moves_to_new_account(self, api, other_api, user, other_user, settings):
        settings.VAPID_PUBLIC_KEY, settings.VAPID_PRIVATE_KEY = "pub", "priv"
        api.post("/api/notifications/push/subscribe/", SUB, format="json")
        other_api.post("/api/notifications/push/subscribe/", SUB, format="json")
        assert PushSubscription.objects.get().user == other_user

    def test_html_email(self, user):
        user.settings.email_notifications = True
        user.settings.save()
        notify(user, "system", "Mail me", body="Body text", url="/reports/")
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.subject == "Mail me" and "Body text" in msg.body
        assert "Open LifeFlow" in msg.alternatives[0].content


def at(user, hour, minute=0, day=None):
    tz = ZoneInfo(user.profile.timezone)
    d = day or date(2026, 3, 4)  # a Wednesday
    return datetime.combine(d, time(hour, minute), tzinfo=tz)


class TestReminders:
    def test_morning_summary_once(self, user):
        make_challenge(user, start=date(2026, 3, 1))
        now = at(user, 8, 5)
        with mock.patch("apps.dashboard.services.user_today", return_value=now.date()), \
             mock.patch("apps.analytics.services.progress.engine.user_today", return_value=now.date()):
            assert reminders.run_for_user(user, now) >= 1
            assert reminders.run_for_user(user, now) == 0  # dedupe
        n = Notification.objects.get(kind="daily_goal")
        assert "challenge" in n.body.lower()

    def test_morning_summary_outside_window(self, user):
        make_challenge(user, start=date(2026, 3, 1))
        with mock.patch("apps.analytics.services.progress.engine.user_today", return_value=date(2026, 3, 4)):
            reminders.run_for_user(user, at(user, 11, 0))
        assert not Notification.objects.filter(kind="daily_goal").exists()

    def test_challenge_reminder_only_when_pending(self, user):
        c = make_challenge(user, start=date(2026, 3, 1))
        c.reminder_time = time(19, 0)
        c.save()
        day = date(2026, 3, 4)
        with mock.patch("apps.analytics.services.progress.engine.user_today", return_value=day):
            reminders.run_for_user(user, at(user, 19, 10))
            assert Notification.objects.filter(kind="challenge_reminder").count() == 1
            # done the next day → no reminder
            add_entry(c, day + timedelta(days=1), amount=2)
        with mock.patch("apps.analytics.services.progress.engine.user_today", return_value=day + timedelta(days=1)):
            reminders.run_for_user(user, at(user, 19, 10, day + timedelta(days=1)))
        assert Notification.objects.filter(kind="challenge_reminder").count() == 1

    def test_activity_reminder(self, user):
        day = date(2026, 3, 4)
        PlannedActivity.objects.create(user=user, title="Gym", date=day, start_time=time(9, 10), end_time=time(10))
        with mock.patch("apps.dashboard.services.user_today", return_value=day):
            reminders.run_for_user(user, at(user, 9, 0))
        assert Notification.objects.filter(kind="activity_reminder", title__contains="Gym").exists()

    def test_disabled_globally(self, user):
        user.settings.notifications_enabled = False
        user.settings.save()
        assert reminders.run_for_user(user, at(user, 8, 5)) == 0

    def test_scheduler_once(self, user):
        from django.core.management import call_command
        call_command("run_scheduler", "--once", verbosity=0)

    def test_notifications_page(self, web, user):
        notify(user, "system", "Visible")
        r = web.get(reverse("notifications:list"))
        assert r.status_code == 200 and b"Visible" in r.content
        web.post(reverse("notifications:read_all"))
        assert not Notification.objects.filter(user=user, is_read=False).exists()

    def test_challenge_reminder_time_api(self, api, user):
        c = make_challenge(user, start=date(2026, 3, 1))
        r = api.patch(f"/api/challenges/{c.pk}/", {"reminder_time": "07:30"}, format="json")
        assert r.status_code == 200 and r.json()["reminder_time"].startswith("07:30")
