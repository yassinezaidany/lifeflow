import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from apps.challenges.models import ChallengeCategory
from apps.planner.models import ActivityCategory

from .factories import make_user

pytestmark = pytest.mark.django_db
User = get_user_model()


class TestWebAuth:
    def test_register_creates_profile_defaults_and_logs_in(self, client):
        r = client.post(reverse("accounts:register"), {
            "first_name": "Yassine", "username": "yassine", "email": "Yassine@Example.com",
            "password": "Very-strong-pass-42", "timezone": "Africa/Casablanca",
        })
        assert r.status_code == 302 and r["Location"] == reverse("accounts:onboarding")
        user = User.objects.get(username="yassine")
        assert user.email == "yassine@example.com"
        assert user.profile.timezone == "Africa/Casablanca"
        assert user.settings is not None
        assert ChallengeCategory.objects.filter(user=user).count() == 10
        assert ActivityCategory.objects.filter(user=user).count() == 12
        assert client.get(reverse("dashboard:home")).status_code == 200

    def test_register_rejects_weak_password_and_duplicates(self, client, user):
        r = client.post(reverse("accounts:register"), {"username": "x1", "email": "a@b.co", "password": "123"})
        assert r.status_code == 200 and not User.objects.filter(username="x1").exists()
        r = client.post(reverse("accounts:register"), {"username": "ALICE", "email": "new@x.co", "password": "Very-strong-pass-42"})
        assert "username" in r.context["form"].errors
        r = client.post(reverse("accounts:register"), {"username": "newone", "email": "ALICE@example.com", "password": "Very-strong-pass-42"})
        assert "email" in r.context["form"].errors

    def test_login_with_username_or_email(self, client, user):
        assert client.post(reverse("accounts:login"), {"username": "alice", "password": "Str0ng-pass!"}).status_code == 302
        client.logout()
        assert client.post(reverse("accounts:login"), {"username": "ALICE@example.com", "password": "Str0ng-pass!"}).status_code == 302

    def test_login_wrong_password(self, client, user):
        r = client.post(reverse("accounts:login"), {"username": "alice", "password": "nope"})
        assert r.status_code == 200 and "_auth_user_id" not in client.session

    def test_login_rate_limit(self, client, user, settings):
        settings.LOGIN_RATE_LIMIT_ATTEMPTS = 3
        for _ in range(3):
            client.post(reverse("accounts:login"), {"username": "alice", "password": "bad"})
        r = client.post(reverse("accounts:login"), {"username": "alice", "password": "Str0ng-pass!"})
        assert r.status_code == 200 and "_auth_user_id" not in client.session

    def test_open_redirect_blocked(self, client, user):
        r = client.post(reverse("accounts:login") + "?next=https://evil.example.com/", {"username": "alice", "password": "Str0ng-pass!", "next": "https://evil.example.com/"})
        assert r["Location"] == reverse("dashboard:home")

    def test_logout_requires_post(self, web):
        assert web.get(reverse("accounts:logout")).status_code == 405
        assert web.post(reverse("accounts:logout")).status_code == 302
        assert web.get(reverse("dashboard:home")).status_code == 302

    def test_password_reset_flow(self, client, user):
        r = client.post(reverse("accounts:password_reset"), {"email": "alice@example.com"})
        assert r.status_code == 302 and len(mail.outbox) == 1
        link = next(line for line in mail.outbox[0].body.splitlines() if "/accounts/password/reset/" in line)
        path = link.split("testserver")[-1].strip()
        r = client.get(path, follow=True)
        assert r.status_code == 200
        r = client.post(r.redirect_chain[-1][0], {"new_password1": "Another-strong-77", "new_password2": "Another-strong-77"})
        assert r.status_code == 302
        user.refresh_from_db()
        assert user.check_password("Another-strong-77")

    def test_unknown_email_reset_does_not_leak(self, client):
        r = client.post(reverse("accounts:password_reset"), {"email": "nobody@example.com"})
        assert r.status_code == 302 and len(mail.outbox) == 0

    def test_change_password(self, web, user):
        r = web.post(reverse("accounts:security"), {"old_password": "Str0ng-pass!", "new_password1": "Brand-new-pass-9", "new_password2": "Brand-new-pass-9"})
        assert r.status_code == 302
        user.refresh_from_db()
        assert user.check_password("Brand-new-pass-9")

    def test_settings_update(self, web, user):
        r = web.post(reverse("accounts:settings"), {
            "account-first_name": "Al", "account-last_name": "", "account-username": "alice", "account-email": "alice@example.com",
            "profile-timezone": "Europe/Paris", "profile-language": "fr", "profile-date_format": "d/m/Y", "profile-time_format": "24h",
            "profile-week_start": 0, "profile-theme": "dark", "profile-planner_slot_minutes": 30, "profile-planner_day_start": 6,
            "profile-planner_day_end": 23, "profile-bio": "",
        })
        assert r.status_code == 302
        user.profile.refresh_from_db()
        assert (user.profile.timezone, user.profile.theme, user.profile.language) == ("Europe/Paris", "dark", "fr")

    def test_delete_account(self, web, user):
        assert web.post(reverse("accounts:delete"), {"password": "wrong"}).status_code == 302
        assert User.objects.filter(pk=user.pk).exists()
        web.post(reverse("accounts:delete"), {"password": "Str0ng-pass!"})
        assert not User.objects.filter(pk=user.pk).exists()


class TestApiAuth:
    def test_api_requires_authentication(self):
        client = APIClient()
        for url in ["/api/challenges/", "/api/planner/activities/", "/api/dashboard/", "/api/reports/", "/api/journal/"]:
            assert client.get(url).status_code in (401, 403), url

    def test_api_register_login_logout_me(self):
        client = APIClient(enforce_csrf_checks=False)
        r = client.post("/api/auth/register/", {"username": "bob2", "email": "bob2@x.co", "password": "Very-strong-pass-42"}, format="json")
        assert r.status_code == 201
        assert client.get("/api/auth/me/").json()["username"] == "bob2"
        assert client.post("/api/auth/logout/").status_code == 204
        assert client.get("/api/auth/me/").status_code in (401, 403)
        r = client.post("/api/auth/login/", {"username": "bob2", "password": "Very-strong-pass-42"}, format="json")
        assert r.status_code == 200

    def test_jwt_token(self):
        make_user("carol")
        client = APIClient()
        r = client.post("/api/auth/token/", {"username": "carol", "password": "Str0ng-pass!"}, format="json")
        assert r.status_code == 200
        client.credentials(HTTP_AUTHORIZATION="Bearer " + r.json()["access"])
        assert client.get("/api/auth/me/").json()["username"] == "carol"

    def test_me_patch_validation(self, api):
        r = api.patch("/api/auth/me/", {"profile": {"planner_day_start": 20, "planner_day_end": 8}}, format="json")
        assert r.status_code == 400
        r = api.patch("/api/auth/me/", {"profile": {"theme": "dark"}}, format="json")
        assert r.status_code == 200 and r.json()["profile"]["theme"] == "dark"

    def test_csrf_enforced_for_session_api(self, user):
        client = APIClient(enforce_csrf_checks=True)
        client.login(username="alice", password="Str0ng-pass!")
        r = client.post("/api/journal/", {"date": "2026-01-01", "content": "x"}, format="json")
        assert r.status_code == 403
