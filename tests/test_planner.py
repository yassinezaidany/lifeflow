from datetime import date, time, timedelta

import pytest

from apps.core.dates import user_today
from apps.planner import services
from apps.planner.models import PlannedActivity, PlannerTemplate, RecurringRule
from apps.tracking.models import ChallengeEntry

from .factories import make_challenge

pytestmark = pytest.mark.django_db
MON = date(2026, 1, 5)  # Monday


def create(api, **kw):
    body = {"title": "Gym", "date": MON.isoformat(), "start_time": "09:00", "end_time": "10:30", **kw}
    return api.post("/api/planner/activities/", body, format="json")


class TestActivities:
    def test_create_and_read(self, api, user):
        r = create(api)
        assert r.status_code == 201, r.json()
        data = r.json()
        assert data["duration_minutes"] == 90 and data["status"] == "planned" and data["overlaps"] == []

    def test_custom_durations_and_midnight(self, api):
        assert create(api, start_time="09:15", end_time="10:45").json()["duration_minutes"] == 90
        assert create(api, start_time="23:00", end_time="00:00").json()["duration_minutes"] == 60

    def test_invalid_time_range(self, api):
        r = create(api, start_time="10:00", end_time="09:00")
        assert r.status_code == 400 and "end_time" in r.json()["errors"]

    def test_overlap_detection(self, api, user):
        create(api)
        r = create(api, title="Call", start_time="10:00", end_time="11:00")
        assert [o["title"] for o in r.json()["overlaps"]] == ["Gym"]
        r = create(api, title="After", start_time="10:30", end_time="11:00")
        assert len(r.json()["overlaps"]) == 1  # only "Call" (10:00-11:00); Gym ends at 10:30

    def test_update_move_duplicate(self, api, user):
        a = create(api).json()
        r = api.patch(f"/api/planner/activities/{a['id']}/", {"title": "Gym session"}, format="json")
        assert r.json()["title"] == "Gym session"
        r = api.post(f"/api/planner/activities/{a['id']}/move/", {"date": (MON + timedelta(days=1)).isoformat(), "start_time": "18:00", "end_time": "19:30"}, format="json")
        assert r.json()["date"] == "2026-01-06" and r.json()["start_time"] == "18:00"
        r = api.post(f"/api/planner/activities/{a['id']}/move/", {"start_time": "20:00", "end_time": "19:00"}, format="json")
        assert r.status_code == 400
        r = api.post(f"/api/planner/activities/{a['id']}/duplicate/", {"date": "2026-01-10"}, format="json")
        assert r.status_code == 201 and r.json()["id"] != a["id"]

    def test_complete_never_creates_entry_automatically(self, api, user):
        c = make_challenge(user, start=MON - timedelta(days=30), fields=[{"label": "Duration", "key": "duration", "field_type": "duration"}],
                           goal={"metric": "duration", "period": "daily", "aggregation": "sum", "target": 30})
        a = create(api, challenge_id=c.pk).json()
        r = api.post(f"/api/planner/activities/{a['id']}/status/", {"status": "completed", "actual_minutes": 80}, format="json")
        assert r.status_code == 200 and r.json()["status"] == "completed"
        assert ChallengeEntry.objects.count() == 0  # planning != succeeding
        suggestion = r.json()["entry_suggestion"]
        assert suggestion["values"] == {"duration": 80} and suggestion["planned_activity"] == a["id"]

    def test_entry_from_activity_requires_completion(self, api, user):
        c = make_challenge(user, start=user_today(user) - timedelta(days=5))
        today = user_today(user).isoformat()
        a = create(api, challenge_id=c.pk, date=today).json()
        r = api.post("/api/entries/", {"challenge": c.pk, "date": today, "values": {"amount": 2}, "planned_activity": a["id"]}, format="json")
        assert r.status_code == 400 and "planned_activity" in r.json()["errors"]
        api.post(f"/api/planner/activities/{a['id']}/status/", {"status": "completed"}, format="json")
        r = api.post("/api/entries/", {"challenge": c.pk, "date": today, "values": {"amount": 2}, "planned_activity": a["id"]}, format="json")
        assert r.status_code == 201 and r.json()["source"] == "planner"

    def test_statuses(self, api):
        a = create(api).json()
        for s in ["in_progress", "partial", "missed", "cancelled", "planned"]:
            assert api.post(f"/api/planner/activities/{a['id']}/status/", {"status": s}, format="json").json()["status"] == s
        assert api.post(f"/api/planner/activities/{a['id']}/status/", {"status": "rescheduled"}, format="json").status_code == 400
        assert api.post(f"/api/planner/activities/{a['id']}/status/", {"status": "nope"}, format="json").status_code == 400

    def test_reschedule(self, api):
        a = create(api).json()
        r = api.post(f"/api/planner/activities/{a['id']}/reschedule/", {"date": "2026-01-07", "start_time": "17:00", "end_time": "18:00"}, format="json")
        assert r.status_code == 201
        assert r.json()["rescheduled_from"] == a["id"] and r.json()["status"] == "planned"
        assert PlannedActivity.objects.get(pk=a["id"]).status == "rescheduled"

    def test_delete_one_off(self, api):
        a = create(api).json()
        assert api.delete(f"/api/planner/activities/{a['id']}/").status_code == 204
        assert not PlannedActivity.objects.filter(pk=a["id"]).exists()


class TestRecurrence:
    def _rule(self, api, **kw):
        body = {"title": "Gym", "start_time": "09:00", "end_time": "10:30", "frequency": "weekly", "weekdays": [0, 2, 4],
                "start_date": MON.isoformat(), **kw}
        return api.post("/api/planner/rules/", body, format="json")

    def test_weekly_rule_materialises_without_duplicates(self, api, user):
        assert self._rule(api).status_code == 201
        r = api.get("/api/planner/week/", {"start": MON.isoformat()})
        titles = [(d["date"], [a["title"] for a in d["activities"]]) for d in r.json()["days"]]
        assert [d for d, t in titles if t] == ["2026-01-05", "2026-01-07", "2026-01-09"]
        api.get("/api/planner/week/", {"start": MON.isoformat()})
        assert PlannedActivity.objects.filter(user=user).count() == 3  # idempotent

    def test_daily_interval_and_end_date(self, api, user):
        self._rule(api, frequency="daily", weekdays=[], end_date=(MON + timedelta(days=2)).isoformat())
        self._rule(api, title="Long run", frequency="interval", interval_days=3)
        services.ensure_occurrences(user, MON, MON + timedelta(days=6))
        assert PlannedActivity.objects.filter(title="Gym").count() == 3
        assert sorted(a.date.day for a in PlannedActivity.objects.filter(title="Long run")) == [5, 8, 11]

    def test_rule_requires_weekdays(self, api):
        assert self._rule(api, weekdays=[]).status_code == 400

    def test_cancelled_occurrence_is_not_recreated(self, api, user):
        self._rule(api)
        services.ensure_occurrences(user, MON, MON)
        occ = PlannedActivity.objects.get(date=MON)
        api.delete(f"/api/planner/activities/{occ.pk}/")
        services.ensure_occurrences(user, MON, MON)
        occ.refresh_from_db()
        assert occ.status == "cancelled" and PlannedActivity.objects.filter(date=MON).count() == 1

    def test_edit_occurrence_detaches_and_rule_update_keeps_it(self, api, user):
        start = user_today(user)
        rule_id = self._rule(api, frequency="daily", weekdays=[], start_date=start.isoformat()).json()["id"]
        services.ensure_occurrences(user, start, start + timedelta(days=3))
        occ = PlannedActivity.objects.get(date=start + timedelta(days=1))
        api.patch(f"/api/planner/activities/{occ.pk}/", {"title": "Special"}, format="json")
        occ.refresh_from_db()
        assert occ.is_detached
        api.patch(f"/api/planner/rules/{rule_id}/", {"start_time": "07:00", "end_time": "08:00"}, format="json")
        services.ensure_occurrences(user, start, start + timedelta(days=3))
        assert PlannedActivity.objects.get(pk=occ.pk).title == "Special"
        others = PlannedActivity.objects.filter(recurring_rule_id=rule_id).exclude(pk=occ.pk)
        assert others.count() == 3 and all(a.start_time == time(7, 0) for a in others)

    def test_delete_rule_keeps_done_history(self, api, user):
        start = user_today(user) - timedelta(days=3)
        rule_id = self._rule(api, frequency="daily", weekdays=[], start_date=start.isoformat()).json()["id"]
        services.ensure_occurrences(user, start, start + timedelta(days=6))
        past = PlannedActivity.objects.get(date=start)
        services.set_status(past, "completed")
        api.delete(f"/api/planner/rules/{rule_id}/")
        assert PlannedActivity.objects.filter(pk=past.pk).exists()
        assert not PlannedActivity.objects.filter(date__gte=user_today(user), status="planned").exists()
        assert not RecurringRule.objects.filter(pk=rule_id).exists()


class TestTemplatesAndViews:
    def test_template_crud_apply_and_from_day(self, api, user):
        cat = user.activity_categories.first()
        r = api.post("/api/planner/templates/", {"name": "University Day", "items": [
            {"title": "Fajr", "start_time": "05:00", "end_time": "05:30", "category_id": cat.pk},
            {"title": "University", "start_time": "08:30", "end_time": "12:00"},
        ]}, format="json")
        assert r.status_code == 201, r.json()
        tid = r.json()["id"]
        r = api.post(f"/api/planner/templates/{tid}/apply/", {"dates": ["2026-01-05", "2026-01-06"]}, format="json")
        assert r.json()["created"] == 4
        r = api.post(f"/api/planner/templates/{tid}/apply/", {"dates": ["2026-01-05"], "replace": True}, format="json")
        assert PlannedActivity.objects.filter(date=MON).count() == 2
        r = api.post("/api/planner/templates/from-day/", {"date": "2026-01-06", "name": "Copy"}, format="json")
        assert r.status_code == 201 and len(r.json()["items"]) == 2
        assert api.post("/api/planner/templates/", {"name": "university day"}, format="json").status_code == 400
        assert api.post(f"/api/planner/templates/{tid}/apply/", {"dates": []}, format="json").status_code == 400

    def test_template_rejects_foreign_category(self, api, other_user):
        cat = other_user.activity_categories.first()
        r = api.post("/api/planner/templates/", {"name": "X", "items": [{"title": "A", "start_time": "05:00", "end_time": "06:00", "category_id": cat.pk}]}, format="json")
        assert r.status_code == 400

    def test_day_today_week_endpoints(self, api, user):
        create(api)
        r = api.get("/api/planner/", {"date": MON.isoformat()})
        assert r.json()["summary"]["planned"] == 1
        assert api.get("/api/planner/today/").status_code == 200
        r = api.get("/api/planner/week/", {"start": "2026-01-07"})
        assert r.json()["start"] == "2026-01-05" and len(r.json()["days"]) == 7

    def test_empty_planning_summary(self, api):
        r = api.get("/api/planner/", {"date": "2030-01-01"})
        assert r.json()["summary"] == {"planned": 0, "completed": 0, "partial": 0, "missed": 0, "remaining": 0,
                                       "planned_minutes": 0, "done_minutes": 0, "completion_rate": None}

    def test_week_start_preference(self, api, user):
        user.profile.week_start = 6
        user.profile.save()
        r = api.get("/api/planner/week/", {"start": "2026-01-07"})
        assert r.json()["start"] == "2026-01-04"  # Sunday

    def test_summary_counts_overdue_as_missed(self, user):
        yesterday = user_today(user) - timedelta(days=1)
        a = PlannedActivity.objects.create(user=user, title="Old", date=yesterday, start_time=time(9), end_time=time(10))
        b = PlannedActivity.objects.create(user=user, title="Done", date=yesterday, start_time=time(11), end_time=time(12), status="completed")
        s = services.summarize([a, b], user)
        assert s["missed"] == 1 and s["completed"] == 1 and s["completion_rate"] == 50

    def test_template_from_empty_day_rejected(self, user):
        with pytest.raises(Exception):
            services.template_from_day(user, date(2031, 1, 1), "Empty")
        assert not PlannerTemplate.objects.filter(name="Empty").exists()
