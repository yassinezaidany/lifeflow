from datetime import date, timedelta

import pytest

from apps.challenges.models import Challenge, ChallengePause, Goal, TrackingField
from apps.core.dates import user_today
from apps.tracking.models import ChallengeEntry

from .factories import make_challenge

pytestmark = pytest.mark.django_db


def wizard_payload(**over):
    payload = {
        "name": "Read 20 pages", "start_date": "2026-01-01", "end_date": "2026-01-30",
        "fields": [{"ref": "primary", "label": "Pages", "field_type": "integer", "unit": "pages"},
                   {"label": "Book", "field_type": "text"}],
        "goal": {"metric": "primary", "period": "daily", "aggregation": "sum", "target": 20},
        "schedule": {"frequency": "daily"},
    }
    payload.update(over)
    return payload


class TestCreate:
    def test_create_via_wizard(self, api, user):
        r = api.post("/api/challenges/", wizard_payload(), format="json")
        assert r.status_code == 201, r.json()
        data = r.json()
        assert [f["key"] for f in data["tracking_fields"]] == ["pages", "book"]
        assert data["goal"]["metric_key"] == "pages"
        assert data["progress"]["goal_description"].startswith("20 pages")
        c = Challenge.objects.get(pk=data["id"])
        assert c.user == user and c.goals.count() == 1 and c.schedules.count() == 1

    def test_sessions_goal_forces_count(self, api):
        r = api.post("/api/challenges/", wizard_payload(fields=[], goal={"metric": None, "period": "weekly", "aggregation": "sum", "target": 3}), format="json")
        assert r.status_code == 201
        assert Goal.objects.get(challenge_id=r.json()["id"]).aggregation == "count"

    @pytest.mark.parametrize("over,field", [
        ({"name": ""}, "name"),
        ({"end_date": "2025-12-01"}, "end_date"),
        ({"goal": {"metric": "primary", "period": "daily", "target": 0}}, "goal"),
        ({"goal": {"metric": "unknown", "period": "daily", "target": 1}}, "goal"),
        ({"goal": {"metric": "Book", "period": "daily", "target": 1}}, "goal"),  # text field is not measurable
        ({"schedule": {"frequency": "weekdays", "weekdays": []}}, "schedule"),
        ({"fields": [{"label": "Type", "field_type": "select", "options": []}]}, "fields"),
        ({"fields": [{"label": "A", "field_type": "integer"}, {"label": "a", "field_type": "integer"}]}, "fields"),
        ({"icon": "not-an-icon"}, "icon"),
        ({"color": "neon"}, "color"),
    ])
    def test_validation(self, api, over, field):
        r = api.post("/api/challenges/", wizard_payload(**over), format="json")
        assert r.status_code == 400
        assert field in r.json()["errors"]

    def test_cannot_use_other_users_category(self, api, other_user):
        cat = other_user.challenge_categories.first()
        r = api.post("/api/challenges/", wizard_payload(category=cat.pk), format="json")
        assert r.status_code == 400 and "category" in r.json()["errors"]

    def test_create_from_template(self, api):
        r = api.get("/api/challenge-templates/")
        tpl = next(t for t in r.json() if t["slug"] == "running-3-week")
        payload = {"name": tpl["name"], "start_date": "2026-01-01", "template": tpl["id"], **tpl["definition"]}
        payload["fields"] = [{**f, "ref": f["key"]} for f in payload["fields"]]
        r = api.post("/api/challenges/", payload, format="json")
        assert r.status_code == 201, r.json()
        goal = Goal.objects.get(challenge_id=r.json()["id"])
        assert goal.min_per_entry == 30 and goal.period == "weekly" and goal.aggregation == "count"


class TestUpdate:
    def test_update_general(self, api, user):
        c = make_challenge(user, start=date(2026, 1, 1))
        r = api.patch(f"/api/challenges/{c.pk}/", {"name": "Renamed", "end_date": "2026-03-01"}, format="json")
        assert r.status_code == 200 and r.json()["name"] == "Renamed"

    def test_goal_versioning_via_api(self, api, user):
        c = make_challenge(user, start=date(2026, 1, 1))
        r = api.put(f"/api/challenges/{c.pk}/goal/", {"metric": "amount", "period": "daily", "aggregation": "sum", "target": 3, "effective_from": "2026-01-16"}, format="json")
        assert r.status_code == 200
        assert len(r.json()["goals_history"]) == 2
        assert r.json()["goal"]["target"] == "3.00"

    def test_goal_effective_before_start_rejected(self, api, user):
        c = make_challenge(user, start=date(2026, 1, 10))
        r = api.put(f"/api/challenges/{c.pk}/goal/", {"metric": None, "period": "daily", "target": 1, "effective_from": "2026-01-01"}, format="json")
        assert r.status_code == 400

    def test_schedule_versioning(self, api, user):
        c = make_challenge(user, start=date(2026, 1, 1))
        r = api.put(f"/api/challenges/{c.pk}/schedule/", {"frequency": "weekdays", "weekdays": [0, 2, 4], "effective_from": "2026-02-01"}, format="json")
        assert r.status_code == 200
        assert c.schedules.count() == 2

    def test_add_and_remove_fields(self, api, user):
        c = make_challenge(user, start=date(2026, 1, 1))
        r = api.post(f"/api/challenges/{c.pk}/fields/", {"label": "Mood", "field_type": "select", "options": ["Good", "Bad"]}, format="json")
        assert r.status_code == 201
        fid = r.json()["id"]
        assert api.delete(f"/api/challenges/{c.pk}/fields/{fid}/").status_code == 204
        assert not TrackingField.objects.filter(pk=fid).exists()
        metric = c.fields.get(key="amount")
        api.delete(f"/api/challenges/{c.pk}/fields/{metric.pk}/")
        metric.refresh_from_db()
        assert metric.is_active is False  # used by the goal: archived, not deleted

    def test_status_transitions(self, api, user):
        c = make_challenge(user, start=user_today(user) - timedelta(days=5))
        assert api.post(f"/api/challenges/{c.pk}/status/", {"status": "paused"}, format="json").json()["status"] == "paused"
        assert ChallengePause.objects.filter(challenge=c, end_date__isnull=True).exists()
        api.post(f"/api/challenges/{c.pk}/status/", {"status": "active"}, format="json")
        assert not ChallengePause.objects.filter(challenge=c, end_date__isnull=True).exists()
        r = api.post(f"/api/challenges/{c.pk}/status/", {"status": "archived"}, format="json")
        assert r.json()["status"] == "archived" and r.json()["closed_on"] is not None
        assert api.post(f"/api/challenges/{c.pk}/status/", {"status": "bogus"}, format="json").status_code == 400

    def test_list_filters_and_delete(self, api, user):
        a = make_challenge(user, name="A", start=date(2026, 1, 1))
        b = make_challenge(user, name="B", start=date(2026, 1, 1))
        b.status = "archived"
        b.save()
        r = api.get("/api/challenges/?status=active")
        assert [x["name"] for x in r.json()["results"]] == ["A"]
        assert r.json()["results"][0]["progress"] is not None
        assert api.delete(f"/api/challenges/{a.pk}/").status_code == 204

    def test_duplicate(self, api, user):
        c = make_challenge(user, start=date(2026, 1, 1))
        r = api.post(f"/api/challenges/{c.pk}/duplicate/", {}, format="json")
        assert r.status_code == 201 and r.json()["name"].endswith("(copy)")

    def test_progress_and_statistics_endpoints(self, api, user):
        c = make_challenge(user, start=user_today(user) - timedelta(days=3))
        r = api.get(f"/api/challenges/{c.pk}/progress/")
        assert r.status_code == 200 and "days" in r.json() and r.json()["status"] in ("behind", "on_track", "ahead")
        r = api.get(f"/api/challenges/{c.pk}/statistics/")
        assert r.status_code == 200 and "statistics" in r.json()

    def test_rest_day_toggle(self, api, user):
        c = make_challenge(user, start=date(2026, 1, 1))
        assert api.post(f"/api/challenges/{c.pk}/rest-day/", {"date": "2026-01-05"}, format="json").json()["rest"] is True
        assert api.post(f"/api/challenges/{c.pk}/rest-day/", {"date": "2026-01-05"}, format="json").json()["rest"] is False
        assert api.post("/api/rest-days/", {"date": "2026-01-06"}, format="json").json()["rest"] is True


class TestEntries:
    def _challenge(self, user, **kw):
        return make_challenge(user, start=user_today(user) - timedelta(days=10), fields=[
            {"label": "Pages", "key": "pages", "field_type": "integer", "unit": "pages", "required": True},
            {"label": "Done", "key": "done", "field_type": "boolean"},
            {"label": "Time", "key": "time", "field_type": "duration"},
            {"label": "Type", "key": "type", "field_type": "select", "options": ["Gym", "Run"]},
            {"label": "Wake", "key": "wake", "field_type": "time"},
            {"label": "Note", "key": "note", "field_type": "text"},
        ], goal={"metric": "pages", "period": "daily", "aggregation": "sum", "target": 2}, **kw)

    def test_create_entry_all_types(self, api, user):
        c = self._challenge(user)
        today = user_today(user).isoformat()
        r = api.post(f"/api/challenges/{c.pk}/entries/", {"date": today, "values": {
            "pages": 4, "done": True, "time": 45, "type": "Gym", "wake": "05:10", "note": "ok"}}, format="json")
        assert r.status_code == 201, r.json()
        assert r.json()["values"] == {"pages": 4, "done": True, "time": 45, "type": "Gym", "wake": "05:10", "note": "ok"}

    @pytest.mark.parametrize("values,field", [
        ({"pages": "abc"}, "pages"), ({"pages": -1}, "pages"), ({"pages": 1.5}, "pages"),
        ({"pages": 1, "type": "Swim"}, "type"), ({"pages": 1, "wake": "25:99"}, "wake"),
        ({"type": "Gym"}, "pages"),  # required field missing
        ({"pages": 1, "unknown": 3}, "values"),
    ])
    def test_entry_validation(self, api, user, values, field):
        c = self._challenge(user)
        r = api.post("/api/entries/", {"challenge": c.pk, "date": user_today(user).isoformat(), "values": values}, format="json")
        assert r.status_code == 400 and field in r.json()["errors"], r.json()

    def test_entry_dates(self, api, user):
        c = self._challenge(user, end=user_today(user) + timedelta(days=5))
        future = (user_today(user) + timedelta(days=1)).isoformat()
        before = (c.start_date - timedelta(days=1)).isoformat()
        for d in (future, before):
            r = api.post("/api/entries/", {"challenge": c.pk, "date": d, "values": {"pages": 2}}, format="json")
            assert r.status_code == 400 and "date" in r.json()["errors"]

    def test_update_and_delete_entry(self, api, user):
        c = self._challenge(user)
        r = api.post("/api/entries/", {"challenge": c.pk, "date": user_today(user).isoformat(), "values": {"pages": 2}}, format="json")
        eid = r.json()["id"]
        r = api.put(f"/api/entries/{eid}/", {"date": user_today(user).isoformat(), "values": {"pages": 5, "done": False}, "note": "edited"}, format="json")
        assert r.status_code == 200 and r.json()["values"]["pages"] == 5 and r.json()["note"] == "edited"
        r = api.patch(f"/api/entries/{eid}/", {"note": "partial"}, format="json")
        assert r.status_code == 200 and r.json()["values"]["pages"] == 5
        assert api.delete(f"/api/entries/{eid}/").status_code == 204
        assert not ChallengeEntry.objects.filter(pk=eid).exists()

    def test_entry_progress_reflected(self, api, user):
        c = self._challenge(user)
        api.post("/api/entries/", {"challenge": c.pk, "date": user_today(user).isoformat(), "values": {"pages": 2}}, format="json")
        r = api.get(f"/api/challenges/{c.pk}/progress/")
        assert r.json()["today"]["done"] is True
