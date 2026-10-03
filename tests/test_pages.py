"""Every page renders (200) for a user with realistic data, and for a brand-new user (empty states)."""
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

from apps.challenges.models import Challenge
from apps.reports.models import MonthlyReport

pytestmark = pytest.mark.django_db

PAGES = [
    "dashboard:home", "dashboard:today", "dashboard:calendar", "planner:week", "planner:rules", "planner:templates",
    "challenges:list", "challenges:create", "challenges:templates", "analytics:overview", "reports:list",
    "journal:list", "journal:new", "journal:review", "accounts:settings", "accounts:notifications",
    "accounts:security", "accounts:categories", "accounts:onboarding",
]


@pytest.fixture
def demo_client(client):
    call_command("seed_demo", verbosity=0)
    user = get_user_model().objects.get(username="demo")
    client.force_login(user)
    return client, user


@pytest.mark.parametrize("name", PAGES)
def test_pages_with_data(demo_client, name):
    client, _ = demo_client
    response = client.get(reverse(name))
    assert response.status_code == 200, name


def test_detail_pages_with_data(demo_client):
    client, user = demo_client
    for c in Challenge.objects.filter(user=user):
        assert client.get(reverse("challenges:detail", args=[c.pk])).status_code == 200
        assert client.get(reverse("challenges:settings", args=[c.pk])).status_code == 200
    for r in MonthlyReport.objects.filter(user=user):
        assert client.get(reverse("reports:detail", args=[r.pk])).status_code == 200
        pdf = client.get(reverse("reports:pdf", args=[r.pk]))
        assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf" and pdf.content[:4] == b"%PDF"
    assert client.get(reverse("dashboard:day", args=["2026-01-15"])).status_code == 200
    assert client.get(reverse("dashboard:calendar") + "?month=2024-02").status_code == 200
    assert client.get(reverse("planner:week") + "?view=day").status_code == 200
    assert client.get(reverse("challenges:list") + "?status=all").status_code == 200
    assert client.get(reverse("challenges:create") + "?template=30-days-reading").status_code == 200
    assert client.get(reverse("analytics:overview") + "?period=year").status_code == 200
    assert client.get(reverse("reports:export") + "?format=xlsx").status_code == 200
    assert client.get(reverse("reports:export") + "?format=csv&kind=statistics").status_code == 200


@pytest.mark.parametrize("name", PAGES)
def test_pages_empty_state(web, name):
    assert web.get(reverse(name)).status_code == 200


def test_french_interface(web, user):
    user.profile.language = "fr"
    user.profile.save()
    content = web.get(reverse("dashboard:home")).content.decode()
    assert "Tableau de bord" in content and "Vos défis" in content


def test_anonymous_redirected_to_login(client):
    for name in ["dashboard:home", "planner:week", "challenges:list"]:
        response = client.get(reverse(name))
        assert response.status_code == 302 and reverse("accounts:login") in response["Location"]
    assert client.get(reverse("accounts:login")).status_code == 200
    assert client.get(reverse("accounts:register")).status_code == 200
    assert client.get(reverse("accounts:password_reset")).status_code == 200
