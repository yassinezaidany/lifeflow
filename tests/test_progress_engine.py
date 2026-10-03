"""Progress engine: Actual, Expected, Goal, Progress, Gap, Status, Streaks, Completion."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.analytics.services.progress import ProgressEngine, ProgressStatus
from apps.challenges.models import Challenge, ChallengePause, RestDay
from apps.challenges.services import change_status, update_goal

from .factories import add_entry, make_challenge, session_entry

pytestmark = pytest.mark.django_db

MON = date(2025, 1, 6)  # a Monday


def evaluate(user, challenge, as_of, **kw):
    challenge = ProgressEngine.prefetch(Challenge.objects.filter(pk=challenge.pk)).get()
    return ProgressEngine(user, as_of=as_of, day_closed=kw.pop("day_closed", False)).evaluate(challenge, **kw)


def days(start, n):
    return [start + timedelta(days=i) for i in range(n)]


class TestDailyGoal:
    def test_spec_example_actual_expected_gap(self, user):
        # 2 pages/day, 10 days elapsed, 18 pages read -> expected 20, gap -2
        c = make_challenge(user, start=MON, end=MON + timedelta(days=29))
        for d in days(MON, 9):
            add_entry(c, d, amount=2)
        r = evaluate(user, c, MON + timedelta(days=10))
        assert r.actual == 18
        assert r.expected == 20
        assert r.gap == -2
        assert r.goal == 60
        assert r.remaining == 42
        assert r.progress == pytest.approx(30.0)
        assert r.status == ProgressStatus.ON_TRACK  # 18/20 = 90% -> within tolerance
        assert r.completion_rate == pytest.approx(90.0)

    def test_progress_90_percent_when_goal_is_20(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=9))
        for d in days(MON, 9):
            add_entry(c, d, amount=2)
        r = evaluate(user, c, MON + timedelta(days=10))
        assert (r.goal, r.actual, r.progress) == (20, 18, 90)
        assert r.status == ProgressStatus.MISSED  # finished below the goal

    def test_overachievement(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=9))
        for d in days(MON, 8):
            add_entry(c, d, amount=3)
        r = evaluate(user, c, MON + timedelta(days=10))
        assert r.actual == 24
        assert r.progress == 120
        assert r.gap == 4
        assert r.remaining == 0
        assert r.status == ProgressStatus.COMPLETED

    def test_today_counts_in_actual_but_not_in_expected(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=29))
        add_entry(c, MON, amount=2)
        r = evaluate(user, c, MON)
        assert r.expected == 0
        assert r.actual == 2
        assert r.status == ProgressStatus.AHEAD
        assert r.today["done"] is True

    def test_behind(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=29))
        add_entry(c, MON, amount=1)
        r = evaluate(user, c, MON + timedelta(days=5))
        assert r.expected == 10
        assert r.status == ProgressStatus.BEHIND

    def test_no_entries(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=29))
        r = evaluate(user, c, MON + timedelta(days=3))
        assert r.actual == 0
        assert r.expected == 6
        assert r.status == ProgressStatus.BEHIND
        assert r.current_streak == 0 and r.best_streak == 0
        assert r.completion_rate == 0

    def test_future_challenge_not_started(self, user):
        c = make_challenge(user, start=MON + timedelta(days=10), end=MON + timedelta(days=19))
        r = evaluate(user, c, MON)
        assert r.status == ProgressStatus.NOT_STARTED
        assert r.actual == 0 and r.expected == 0
        assert r.goal == 20

    def test_open_ended_goal_is_to_date(self, user):
        c = make_challenge(user, start=MON)
        for d in days(MON, 5):
            add_entry(c, d, amount=2)
        r = evaluate(user, c, MON + timedelta(days=4))
        assert r.goal == 10  # 5 days including today
        assert r.expected == 8
        assert r.status == ProgressStatus.AHEAD

    def test_entries_outside_range_ignored(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=6))
        add_entry(c, MON - timedelta(days=1), amount=5)
        add_entry(c, MON + timedelta(days=8), amount=5)
        r = evaluate(user, c, MON + timedelta(days=10))
        assert r.actual == 0


class TestSchedulesAndRestDays:
    def test_weekday_schedule_rest_days_do_not_lower_performance(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=13),
                           goal={"metric": None, "period": "daily", "aggregation": "count", "target": 1},
                           schedule={"frequency": "weekdays", "weekdays": [0, 2, 4]})
        for d in days(MON, 14):
            if d.weekday() in (0, 2, 4):
                session_entry(c, d)
        r = evaluate(user, c, MON + timedelta(days=14))
        assert r.goal == 6
        assert r.actual == 6
        assert r.completion_rate == 100
        assert r.current_streak == 6
        assert r.statistics["rest_days"] == 8
        assert r.status == ProgressStatus.COMPLETED

    def test_explicit_rest_day_keeps_streak(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=29))
        RestDay.objects.create(user=user, challenge=c, date=MON + timedelta(days=2))
        for d in days(MON, 5):
            if d != MON + timedelta(days=2):
                add_entry(c, d, amount=2)
        r = evaluate(user, c, MON + timedelta(days=5))
        assert r.expected == 8  # 4 active elapsed days
        assert r.current_streak == 4
        assert r.completion_rate == 100

    def test_global_rest_day_applies_to_all_challenges(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=29))
        RestDay.objects.create(user=user, challenge=None, date=MON + timedelta(days=1))
        r = evaluate(user, c, MON + timedelta(days=3))
        assert r.expected == 4

    def test_missed_day_breaks_streak_and_best_streak_kept(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=29))
        for d in days(MON, 4):
            add_entry(c, d, amount=2)
        # day 4 missed
        for d in days(MON + timedelta(days=5), 2):
            add_entry(c, d, amount=2)
        r = evaluate(user, c, MON + timedelta(days=7))
        assert r.best_streak == 4
        assert r.current_streak == 2

    def test_pending_today_does_not_break_streak(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=29))
        for d in days(MON, 3):
            add_entry(c, d, amount=2)
        r = evaluate(user, c, MON + timedelta(days=3))
        assert r.current_streak == 3
        assert r.today["status"] == "pending"

    def test_interval_schedule(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=9),
                           schedule={"frequency": "interval", "interval_days": 3})
        r = evaluate(user, c, MON + timedelta(days=10))
        assert r.goal == 8  # days 0,3,6,9 -> 4 active days x 2

    def test_partial_daily_target_is_not_completed(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=9))
        add_entry(c, MON, amount=1)
        r = evaluate(user, c, MON + timedelta(days=1), include_series=True)
        assert r.completion_rate == 0
        assert r.days[0].status == "partial"


class TestPause:
    def test_paused_days_are_excluded(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=29))
        for d in days(MON, 3):
            add_entry(c, d, amount=2)
        ChallengePause.objects.create(challenge=c, start_date=MON + timedelta(days=3), end_date=MON + timedelta(days=6))
        for d in days(MON + timedelta(days=7), 2):
            add_entry(c, d, amount=2)
        r = evaluate(user, c, MON + timedelta(days=9))
        assert r.expected == 10  # 5 active elapsed days
        assert r.goal == 52     # 26 non-paused days
        assert r.current_streak == 5
        assert r.statistics["paused_days"] == 4

    def test_paused_status(self, user):
        c = make_challenge(user, start=date(2020, 1, 1))
        change_status(c, Challenge.Status.PAUSED)
        r = evaluate(user, c, date(2020, 1, 10))
        assert r.status == ProgressStatus.PAUSED


class TestWeeklyMonthlyTotal:
    def test_weekly_expected_is_prorated_within_week(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=27),
                           goal={"metric": None, "period": "weekly", "aggregation": "count", "target": 3})
        for d in (MON + timedelta(days=1), MON + timedelta(days=3), MON + timedelta(days=4), MON + timedelta(days=8)):
            session_entry(c, d)
        r = evaluate(user, c, MON + timedelta(days=10))  # Thursday of week 2
        assert r.goal == 12
        assert r.actual == 4
        assert r.expected == pytest.approx(3 + 3 * 3 / 7)
        assert r.status == ProgressStatus.ON_TRACK
        assert r.completion_rate == 100  # week 1 achieved
        assert r.current_streak == 1
        assert r.streak_unit == "week"
        assert r.today["remaining"] == 2

    def test_weekly_partial_first_week_prorated(self, user):
        wed = MON + timedelta(days=2)
        c = make_challenge(user, start=wed, end=MON + timedelta(days=13),
                           goal={"metric": None, "period": "weekly", "aggregation": "count", "target": 7})
        r = evaluate(user, c, wed)
        assert r.goal == pytest.approx(5 + 7)

    def test_weekly_min_per_entry(self, user):
        # Running: 3 sessions/week, at least 30 minutes
        c = make_challenge(user, start=MON, end=MON + timedelta(days=6),
                           fields=[{"label": "Duration", "key": "duration", "field_type": "duration"}],
                           goal={"metric": "duration", "period": "weekly", "aggregation": "count", "target": 3, "min_per_entry": 30})
        add_entry(c, MON, duration=45)
        add_entry(c, MON + timedelta(days=2), duration=20)  # too short
        add_entry(c, MON + timedelta(days=4), duration=30)
        r = evaluate(user, c, MON + timedelta(days=7))
        assert r.actual == 2
        assert r.status == ProgressStatus.MISSED

    def test_monthly_duration_goal(self, user):
        c = make_challenge(user, start=date(2025, 1, 1), end=date(2025, 3, 31),
                           fields=[{"label": "Duration", "key": "duration", "field_type": "duration"}],
                           goal={"metric": "duration", "period": "monthly", "aggregation": "sum", "target": 1200})
        add_entry(c, date(2025, 1, 10), duration=600)
        add_entry(c, date(2025, 1, 20), duration=700)
        r = evaluate(user, c, date(2025, 2, 1))
        assert r.expected == pytest.approx(1200)
        assert r.actual == 1300
        assert r.goal == pytest.approx(3600)
        assert r.is_duration
        assert r.display["actual"] == "21h40"
        assert r.completion_rate == 100

    def test_total_goal_with_end_date(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=9),
                           fields=[{"label": "Hours", "key": "hours", "field_type": "decimal", "unit": "h"}],
                           goal={"metric": "hours", "period": "total", "aggregation": "sum", "target": 100})
        for d in days(MON, 4):
            add_entry(c, d, hours=12)
        r = evaluate(user, c, MON + timedelta(days=4))
        assert r.goal == 100
        assert r.actual == 48
        assert r.expected == pytest.approx(40)
        assert r.status == ProgressStatus.AHEAD
        assert r.current_streak == 4

    def test_total_goal_reached_is_completed(self, user):
        c = make_challenge(user, start=MON,
                           fields=[{"label": "Hours", "key": "hours", "field_type": "decimal"}],
                           goal={"metric": "hours", "period": "total", "aggregation": "sum", "target": 10})
        add_entry(c, MON, hours=10)
        r = evaluate(user, c, MON + timedelta(days=1))
        assert r.expected is None
        assert r.status == ProgressStatus.COMPLETED

    def test_boolean_daily_goal_false_does_not_count(self, user):
        c = make_challenge(user, start=MON, end=MON + timedelta(days=6),
                           fields=[{"label": "Done", "key": "done", "field_type": "boolean"}],
                           goal={"metric": "done", "period": "daily", "aggregation": "count", "target": 1})
        add_entry(c, MON, done=True)
        add_entry(c, MON + timedelta(days=1), done=False)
        r = evaluate(user, c, MON + timedelta(days=2))
        assert r.actual == 1
        assert r.completion_rate == 50
        assert r.unit == "days"


class TestCalendarEdges:
    def test_leap_year_month_proration(self, user):
        c = make_challenge(user, start=date(2024, 2, 15), end=date(2024, 2, 29),
                           goal={"metric": "amount", "period": "monthly", "aggregation": "sum", "target": 29})
        r = evaluate(user, c, date(2024, 2, 15))
        assert r.goal == pytest.approx(15)  # 15 of the 29 days of February 2024

    def test_month_boundaries_daily(self, user):
        c = make_challenge(user, start=date(2025, 1, 30), end=date(2025, 2, 2))
        for d in days(date(2025, 1, 30), 4):
            add_entry(c, d, amount=2)
        r = evaluate(user, c, date(2025, 2, 3), include_series=True)
        assert r.actual == 8 and r.status == ProgressStatus.COMPLETED
        assert [m["month"] for m in r.statistics["monthly"]] == ["2025-01", "2025-02"]

    def test_window_restricts_to_month(self, user):
        c = make_challenge(user, start=date(2025, 1, 1), end=date(2025, 3, 31))
        for d in days(date(2025, 1, 1), 31):
            add_entry(c, d, amount=2)
        add_entry(c, date(2025, 2, 1), amount=2)
        r = evaluate(user, c, date(2025, 1, 31), day_closed=True, window=(date(2025, 1, 1), date(2025, 1, 31)))
        assert r.goal == 62 and r.actual == 62 and r.expected == 62
        assert r.status == ProgressStatus.COMPLETED


class TestVersioning:
    def test_goal_change_preserves_history(self, user):
        c = make_challenge(user, start=date(2025, 10, 1), end=date(2025, 10, 31))
        update_goal(c, {"metric": c.fields.get(key="amount"), "period": "daily", "aggregation": "sum",
                        "target": Decimal("3"), "min_per_entry": None}, effective_from=date(2025, 10, 16))
        assert c.goals.count() == 2
        r = evaluate(user, c, date(2025, 11, 1))
        assert r.goal == 15 * 2 + 16 * 3
        old = c.goals.order_by("effective_from").first()
        assert old.effective_to == date(2025, 10, 15) and old.target == 2

    def test_goal_change_on_start_day_edits_in_place(self, user):
        c = make_challenge(user, start=date(2025, 10, 1))
        update_goal(c, {"metric": None, "period": "weekly", "aggregation": "count", "target": Decimal("4"), "min_per_entry": None},
                    effective_from=date(2025, 10, 1))
        assert c.goals.count() == 1


class TestMilestones:
    def test_milestones_reached(self, user):
        c = make_challenge(user, start=MON, milestones=[{"title": "5", "target_value": 5}, {"title": "50", "target_value": 50}])
        for d in days(MON, 3):
            add_entry(c, d, amount=2)
        r = evaluate(user, c, MON + timedelta(days=3))
        assert r.milestones[0]["reached"] and r.milestones[0]["reached_on"] == (MON + timedelta(days=2)).isoformat()
        assert not r.milestones[1]["reached"]
