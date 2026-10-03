"""Data isolation: user B can never read or modify user A's data (API and web)."""
from datetime import date, time

import pytest
from django.urls import reverse

from apps.journal.models import JournalEntry
from apps.planner.models import PlannedActivity, PlannerTemplate, RecurringRule
from apps.reports.services.monthly import generate_monthly_report
from apps.tracking.models import ChallengeEntry

from .factories import add_entry, make_challenge

pytestmark = pytest.mark.django_db


@pytest.fixture
def alice_data(user):
    c = make_challenge(user, start=date(2025, 1, 1))
    e = add_entry(c, date(2025, 1, 2), amount=3)
    a = PlannedActivity.objects.create(user=user, title="Secret", date=date(2026, 1, 5), start_time=time(9), end_time=time(10))
    rule = RecurringRule.objects.create(user=user, title="R", start_time=time(9), end_time=time(10), frequency="daily", start_date=date(2026, 1, 1))
    tpl = PlannerTemplate.objects.create(user=user, name="T")
    j = JournalEntry.objects.create(user=user, date=date(2026, 1, 1), content="private")
    report = generate_monthly_report(user, 2025, 1)
    return {"challenge": c, "entry": e, "activity": a, "rule": rule, "template": tpl, "journal": j, "report": report}


def test_lists_do_not_leak(other_api, alice_data):
    for url in ["/api/challenges/", "/api/entries/", "/api/planner/activities/", "/api/journal/", "/api/reports/", "/api/notifications/"]:
        data = other_api.get(url).json()
        assert data["count"] == 0, url
    for url in ["/api/planner/rules/", "/api/planner/templates/"]:
        assert other_api.get(url).json() == [], url
    week = other_api.get("/api/planner/week/", {"start": "2026-01-05"}).json()
    assert all(not d["activities"] for d in week["days"])
    assert other_api.get("/api/dashboard/").json()["challenges"] == []


@pytest.mark.parametrize("method,url,body", [
    ("get", "/api/challenges/{challenge}/", None),
    ("patch", "/api/challenges/{challenge}/", {"name": "hacked"}),
    ("delete", "/api/challenges/{challenge}/", None),
    ("get", "/api/challenges/{challenge}/progress/", None),
    ("post", "/api/challenges/{challenge}/status/", {"status": "archived"}),
    ("put", "/api/challenges/{challenge}/goal/", {"period": "daily", "target": 1}),
    ("post", "/api/challenges/{challenge}/fields/", {"label": "x", "field_type": "text"}),
    ("get", "/api/challenges/{challenge}/entries/", None),
    ("post", "/api/challenges/{challenge}/entries/", {"date": "2025-01-03", "values": {"amount": 1}}),
    ("get", "/api/entries/{entry}/", None),
    ("put", "/api/entries/{entry}/", {"date": "2025-01-03", "values": {"amount": 1}}),
    ("delete", "/api/entries/{entry}/", None),
    ("get", "/api/planner/activities/{activity}/", None),
    ("patch", "/api/planner/activities/{activity}/", {"title": "x"}),
    ("post", "/api/planner/activities/{activity}/status/", {"status": "completed"}),
    ("post", "/api/planner/activities/{activity}/move/", {"date": "2026-01-06"}),
    ("delete", "/api/planner/activities/{activity}/", None),
    ("patch", "/api/planner/rules/{rule}/", {"title": "x"}),
    ("post", "/api/planner/templates/{template}/apply/", {"dates": ["2026-01-05"]}),
    ("get", "/api/journal/{journal}/", None),
    ("get", "/api/reports/{report}/", None),
    ("get", "/api/reports/{report}/pdf/", None),
])
def test_cross_user_access_returns_404(other_api, alice_data, method, url, body):
    url = url.format(**{k: v.pk for k, v in alice_data.items()})
    r = getattr(other_api, method)(url, body, format="json") if body is not None else getattr(other_api, method)(url)
    assert r.status_code == 404, (url, r.status_code)


def test_cannot_attach_entry_to_foreign_challenge_or_activity(other_api, other_user, alice_data):
    r = other_api.post("/api/entries/", {"challenge": alice_data["challenge"].pk, "date": "2025-01-03", "values": {"amount": 1}}, format="json")
    assert r.status_code == 404
    mine = make_challenge(other_user, start=date(2025, 1, 1))
    r = other_api.post("/api/entries/", {"challenge": mine.pk, "date": "2025-01-03", "values": {"amount": 1}, "planned_activity": alice_data["activity"].pk}, format="json")
    assert r.status_code == 400
    r = other_api.post("/api/planner/activities/", {"title": "x", "date": "2026-01-05", "start_time": "09:00", "end_time": "10:00",
                                                     "challenge_id": alice_data["challenge"].pk}, format="json")
    assert r.status_code == 400


def test_alice_data_untouched(other_api, alice_data):
    other_api.patch(f"/api/challenges/{alice_data['challenge'].pk}/", {"name": "hacked"}, format="json")
    other_api.delete(f"/api/entries/{alice_data['entry'].pk}/")
    alice_data["challenge"].refresh_from_db()
    assert alice_data["challenge"].name == "Challenge"
    assert ChallengeEntry.objects.filter(pk=alice_data["entry"].pk).exists()


def test_web_pages_isolated(client, other_user, alice_data):
    client.force_login(other_user)
    assert client.get(reverse("challenges:detail", args=[alice_data["challenge"].pk])).status_code == 404
    assert client.get(reverse("challenges:settings", args=[alice_data["challenge"].pk])).status_code == 404
    assert client.get(reverse("reports:detail", args=[alice_data["report"].pk])).status_code == 404
    assert client.get(reverse("reports:pdf", args=[alice_data["report"].pk])).status_code == 404
    assert client.post(reverse("reports:delete", args=[alice_data["report"].pk])).status_code == 404
    assert client.get(reverse("journal:detail", args=[alice_data["journal"].pk])).status_code == 404
    response = client.get(reverse("dashboard:calendar") + "?month=2026-01&date=2026-01-05")
    assert b"Secret" not in response.content
    export = client.get(reverse("reports:export") + "?format=csv&kind=entries")
    assert b"Challenge" not in export.content.split(b"\n", 1)[1]
