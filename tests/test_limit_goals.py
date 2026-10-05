"""Limit goals ("at most"): a period succeeds while its total stays under the target."""
from datetime import date, timedelta

import pytest

from apps.analytics.services.progress import ProgressEngine, ProgressStatus
from apps.challenges.models import Challenge, Goal

from .factories import add_entry, make_challenge, session_entry

pytestmark = pytest.mark.django_db
MON = date(2025, 1, 6)


def limit_challenge(user, **kw):
    return make_challenge(user, start=MON, end=kw.pop("end", MON + timedelta(days=29)),
                          fields=[{"label": "Screen", "key": "screen", "field_type": "duration"}],
                          goal={"metric": "screen", "period": kw.pop("period", "daily"), "aggregation": "sum",
                                "target": kw.pop("target", 120), "direction": "at_most"})


def evaluate(user, c, as_of, **kw):
    c = ProgressEngine.prefetch(Challenge.objects.filter(pk=c.pk)).get()
    return ProgressEngine(user, as_of=as_of, day_closed=kw.pop("day_closed", False)).evaluate(c, **kw)


def test_daily_limit_completion_streak_and_budget(user):
    c = limit_challenge(user)
    add_entry(c, MON, screen=100)                       # within
    add_entry(c, MON + timedelta(days=1), screen=150)   # over
    # day 3: nothing recorded -> 0 -> within
    r = evaluate(user, c, MON + timedelta(days=3), include_series=True)
    assert (r.completed_periods, r.due_periods) == (2, 3)
    assert r.completion_rate == pytest.approx(66.67, abs=0.01) and r.progress == pytest.approx(66.67, abs=0.01)
    assert r.current_streak == 1 and r.best_streak == 1
    assert r.expected == 480 and r.actual == 250 and r.gap == 230   # positive gap = under budget
    assert r.status == ProgressStatus.AHEAD
    assert [d.status for d in r.days] == ["done", "missed", "done", "pending"]
    assert r.today["status"] == "within" and r.today["done"] is False
    assert r.goal_description.startswith("max.")


def test_exceeding_today_counts_immediately(user):
    c = limit_challenge(user)
    add_entry(c, MON, screen=200)
    r = evaluate(user, c, MON)
    assert r.today["status"] == "over" and r.due_periods == 1 and r.completed_periods == 0
    assert r.progress == 0 and r.status == ProgressStatus.BEHIND


def test_weekly_limit_and_end_states(user):
    c = limit_challenge(user, period="weekly", target=300, end=MON + timedelta(days=6))
    for d in range(5):
        add_entry(c, MON + timedelta(days=d), screen=50)
    r = evaluate(user, c, MON + timedelta(days=7))
    assert r.actual == 250 and r.status == ProgressStatus.COMPLETED and r.completion_rate == 100
    add_entry(c, MON + timedelta(days=5), screen=100)
    r = evaluate(user, c, MON + timedelta(days=7))
    assert r.status == ProgressStatus.MISSED and r.completion_rate == 0


def test_session_count_limit(user):
    c = make_challenge(user, start=MON, end=MON + timedelta(days=6), fields=[],
                       goal={"metric": None, "period": "daily", "target": 2, "direction": "at_most"})
    for _ in range(3):
        session_entry(c, MON)
    r = evaluate(user, c, MON + timedelta(days=1))
    assert r.completed_periods == 0 and r.due_periods == 1


def test_api_validation(api):
    base = {"name": "Coffee", "start_date": "2026-01-05"}
    ok = api.post("/api/challenges/", {**base, "fields": [], "goal": {"metric": None, "period": "daily", "target": 2, "direction": "at_most"}}, format="json")
    assert ok.status_code == 201 and ok.json()["goal"]["direction"] == "at_most"
    goal = Goal.objects.get(challenge_id=ok.json()["id"])
    assert goal.aggregation == "count" and goal.min_per_entry is None
    bad = api.post("/api/challenges/", {**base, "fields": [{"ref": "d", "label": "Done", "field_type": "boolean"}],
                                        "goal": {"metric": "d", "period": "daily", "target": 1, "direction": "at_most"}}, format="json")
    assert bad.status_code == 400 and "direction" in bad.json()["errors"]


def test_screen_time_template(api):
    assert "screen-time-limit" in [t["slug"] for t in api.get("/api/challenge-templates/").json()]
