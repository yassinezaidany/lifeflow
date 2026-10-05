"""Rule-based insights and on-the-fly achievements."""
from datetime import timedelta

import pytest

from apps.analytics.services.achievements import build_achievements
from apps.analytics.services.insights import build_insights
from apps.core.dates import user_today
from apps.dashboard.services import challenge_cards
from apps.planner.models import PlannedActivity

from .factories import add_entry, make_challenge

pytestmark = pytest.mark.django_db


def kinds(user):
    return [i.kind for i in build_insights(user, challenge_cards(user))]


def test_streak_at_risk_and_milestone(user):
    today = user_today(user)
    c = make_challenge(user, name="Pages", start=today - timedelta(days=5),
                       milestones=[{"title": "Ten pages", "target_value": 12}])
    for i in range(5, 0, -1):
        add_entry(c, today - timedelta(days=i), amount=2)
    result = kinds(user)
    assert "streak_at_risk" in result and "milestone_close" in result
    assert result.index("streak_at_risk") < result.index("milestone_close")   # sorted by priority
    add_entry(c, today, amount=2)
    assert "streak_at_risk" not in kinds(user)


def test_behind_suggests_planner_and_inactive(user):
    today = user_today(user)
    make_challenge(user, name="Run", start=today - timedelta(days=6))
    insights = {i.kind: i for i in build_insights(user, challenge_cards(user))}
    assert insights["behind"].url == "/planner/"
    assert "Run" in insights["behind"].text
    assert "inactive" not in insights   # no entries at all yet: nothing to come back to


def test_limit_exceeded_today(user):
    today = user_today(user)
    make_challenge(user, name="Screen", start=today - timedelta(days=2),
                   fields=[{"label": "Screen", "key": "screen", "field_type": "duration"}],
                   goal={"metric": "screen", "period": "daily", "aggregation": "sum", "target": 60, "direction": "at_most"})
    from apps.challenges.models import Challenge
    add_entry(Challenge.objects.get(name="Screen"), today, screen=90)
    assert kinds(user)[0] == "limit_over"


def test_planner_trend(user):
    today = user_today(user)
    for i in range(1, 15):
        day = today - timedelta(days=i)
        status = PlannedActivity.Status.COMPLETED if i <= 7 else PlannedActivity.Status.MISSED
        PlannedActivity.objects.create(user=user, title="Focus", date=day, start_time="09:00", end_time="10:00", status=status)
    assert "planner_up" in kinds(user)


def test_insights_shown_on_dashboard_and_analytics(web, user):
    today = user_today(user)
    make_challenge(user, name="Run", start=today - timedelta(days=6))
    assert b'data-insight="behind"' in web.get("/dashboard/").content
    assert b'data-insight="behind"' in web.get("/analytics/").content


def test_achievements_reflect_real_data_only(user, web):
    today = user_today(user)
    data = build_achievements(user)
    assert data["earned"] == 0 and data["total"] == len(data["items"])
    c = make_challenge(user, start=today - timedelta(days=8))
    for i in range(8, 0, -1):
        add_entry(c, today - timedelta(days=i), amount=2)
    # A planned-but-unconfirmed activity does not count
    PlannedActivity.objects.create(user=user, title="Plan", date=today, start_time="09:00", end_time="10:00")
    earned = {a.key for a in build_achievements(user)["items"] if a.earned}
    assert {"first-step", "streak-7"} <= earned
    assert "planner-10" not in earned and "streak-30" not in earned
    page = web.get("/analytics/achievements/")
    assert page.status_code == 200 and b'data-achievement="streak-7" data-earned="1"' in page.content


def test_achievements_are_per_user(user, other_user):
    today = user_today(user)
    c = make_challenge(other_user, start=today - timedelta(days=3))
    add_entry(c, today - timedelta(days=1), amount=2)
    assert build_achievements(user)["earned"] == 0
    assert build_achievements(other_user)["earned"] >= 1


def test_builtin_templates_are_localized(web, user):
    user.profile.language = "fr"
    user.profile.save()
    from django.utils import translation
    with translation.override("fr"):
        page = web.get("/challenges/templates/", HTTP_ACCEPT_LANGUAGE="fr")
    assert "Lecture du Coran".encode() in page.content
    from apps.challenges.models import ChallengeTemplate
    from apps.challenges.serializers import ChallengeTemplateSerializer
    tpl = ChallengeTemplate.objects.get(owner=None, slug="quran-reading")
    with translation.override("ar"):
        data = ChallengeTemplateSerializer(tpl).data
    assert data["name"] == "قراءة القرآن" and data["definition"]["fields"][1]["label"] == "السورة"
    assert ChallengeTemplate.objects.get(pk=tpl.pk).name == "Qur'an Reading"   # stored in English
