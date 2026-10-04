import json
from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest import mock

import pytest
from django.urls import reverse

from apps.analytics.services.progress import ProgressEngine, ProgressStatus
from apps.challenges import assistant
from apps.challenges.models import Challenge, Goal
from apps.planner.models import PlannedActivity
from apps.reports.generators.pdf import render_monthly_report_pdf, shape
from apps.reports.services.monthly import generate_monthly_report
from apps.tracking.models import ChallengeEntry, EntryFieldValue

from .factories import make_challenge

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------- assistant
class TestRuleParser:
    def test_french_learning_hours(self):
        s = assistant.sanitize(assistant.rule_based_suggest("Je veux apprendre Python 2 heures par jour pendant 30 jours"))
        assert s["name"] == "Apprendre Python"
        assert s["duration_days"] == 30 and s["category_name"] == "Learning" and s["icon"] == "code"
        g = s["definition"]["goal"]
        assert (g["metric"], g["period"], g["aggregation"], g["target"]) == ("duration", "daily", "sum", 120)
        assert [f["field_type"] for f in s["definition"]["fields"]] == ["duration", "text"]

    def test_english_sessions_with_minimum(self):
        s = assistant.sanitize(assistant.rule_based_suggest("I want to run 3 times a week, at least 30 minutes, for 3 months"))
        g = s["definition"]["goal"]
        assert (g["period"], g["aggregation"], g["target"], g["min_per_entry"], g["metric"]) == ("weekly", "count", 3, 30, "duration")
        assert s["duration_days"] == 90 and s["icon"] == "footprints"

    def test_pages_and_weekdays(self):
        s = assistant.sanitize(assistant.rule_based_suggest("Lire 20 pages le lundi, mercredi et vendredi"))
        assert s["definition"]["schedule"] == {"frequency": "weekdays", "weekdays": [0, 2, 4], "interval_days": 1}
        assert s["definition"]["goal"]["target"] == 20 and s["definition"]["fields"][0]["unit"] == "pages"

    def test_boolean_habit(self):
        s = assistant.sanitize(assistant.rule_based_suggest("Méditer chaque jour"))
        g = s["definition"]["goal"]
        assert s["definition"]["fields"][0]["field_type"] == "boolean" and g["aggregation"] == "count" and g["target"] == 1

    def test_arabic(self):
        s = assistant.sanitize(assistant.rule_based_suggest("أريد قراءة القرآن صفحتين يوميا لمدة 30 يوما"))
        assert s["duration_days"] == 30 and s["icon"] == "book-marked" and s["definition"]["goal"]["period"] == "daily"

    def test_water_decimal(self):
        s = assistant.sanitize(assistant.rule_based_suggest("Boire 2,5 litres d'eau par jour"))
        f = s["definition"]["fields"][0]
        assert f["field_type"] == "decimal" and f["unit"] == "L" and s["definition"]["goal"]["target"] == 2.5


class TestSanitize:
    def test_untrusted_output_is_coerced(self):
        s = assistant.sanitize({
            "name": "x" * 300, "icon": "<script>", "color": "neon", "category": "Hacking", "duration_days": 99999,
            "fields": [{"key": "Pagès lues!", "label": "Pages", "field_type": "integer", "unit": "pages", "options": []},
                       {"key": "t", "label": "Type", "field_type": "select", "options": []}],
            "goal": {"metric": "unknown", "period": "yearly", "aggregation": "max", "target": -5, "min_per_entry": "abc"},
            "schedule": {"frequency": "weekdays", "weekdays": [9, -1], "interval_days": 0},
        })
        assert len(s["name"]) == 100 and s["icon"] == "target" and s["color"] == "indigo" and s["category_name"] == "Other"
        assert s["duration_days"] is None
        assert s["definition"]["fields"][0]["key"] == "pages_lues" and s["definition"]["fields"][1]["field_type"] == "text"
        g = s["definition"]["goal"]
        assert g == {"metric": None, "period": "daily", "aggregation": "count", "target": 0.01, "min_per_entry": None}
        assert s["definition"]["schedule"]["frequency"] == "daily"


class TestSuggestEndpoint:
    def test_rules_engine_without_key(self, api):
        r = api.post("/api/challenges/suggest/", {"text": "Faire 10000 pas par jour"}, format="json")
        assert r.status_code == 200 and r.json()["source"] == "rules"
        assert r.json()["definition"]["goal"]["target"] == 10000
        assert api.post("/api/challenges/suggest/", {"text": "x"}, format="json").status_code == 400
        assert api.post("/api/challenges/suggest/", {"text": "a" * 501}, format="json").status_code == 400

    def test_claude_engine_mocked(self, api, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        payload = {
            "name": "Learn Python", "description": "", "category": "Learning", "icon": "code", "color": "violet", "duration_days": 30,
            "fields": [{"key": "duration", "label": "Duration", "field_type": "duration", "unit": "", "options": []}],
            "goal": {"metric": "duration", "period": "daily", "aggregation": "sum", "target": 120, "min_per_entry": None},
            "schedule": {"frequency": "daily", "weekdays": [], "interval_days": 1},
        }
        fake = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(payload))])
        with mock.patch("anthropic.Anthropic") as client_cls:
            client_cls.return_value.beta.messages.create.return_value = fake
            r = api.post("/api/challenges/suggest/", {"text": "Learn Python 2h a day for 30 days"}, format="json")
            kwargs = client_cls.return_value.beta.messages.create.call_args.kwargs
        assert r.json()["source"] == "ai" and r.json()["name"] == "Learn Python"
        assert kwargs["model"] == "claude-opus-5-5" and kwargs["output_config"]["format"]["type"] == "json_schema"
        assert kwargs["fallbacks"] == "default"

    def test_claude_refusal_falls_back_to_rules(self, api, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        fake = SimpleNamespace(stop_reason="refusal", content=[])
        with mock.patch("anthropic.Anthropic") as client_cls:
            client_cls.return_value.beta.messages.create.return_value = fake
            r = api.post("/api/challenges/suggest/", {"text": "Lire 20 pages par jour"}, format="json")
        assert r.json()["source"] == "rules"

    def test_suggestion_creates_valid_challenge(self, api):
        s = api.post("/api/challenges/suggest/", {"text": "Courir 3 fois par semaine au moins 30 minutes"}, format="json").json()
        payload = {"name": s["name"], "start_date": "2026-01-05", "icon": s["icon"], "color": s["color"], **s["definition"]}
        assert api.post("/api/challenges/", payload, format="json").status_code == 201


# ---------------------------------------------------------------------------- time goals
class TestTimeGoal:
    def _challenge(self, user):
        return make_challenge(user, start=date(2026, 1, 5), end=date(2026, 1, 11),
                              fields=[{"label": "Wake-up", "key": "wake", "field_type": "time"}],
                              goal={"metric": "wake", "period": "daily", "aggregation": "count", "target": 1,
                                    "time_comparison": "before", "time_threshold": time(5, 30)})

    def test_counts_days_before_threshold(self, user):
        c = self._challenge(user)
        for day, at in ((5, time(5, 10)), (6, time(5, 30)), (7, time(6, 0))):
            e = ChallengeEntry.objects.create(user=user, challenge=c, date=date(2026, 1, day))
            EntryFieldValue.objects.create(entry=e, field=c.fields.get(key="wake"), value_time=at)
        c = ProgressEngine.prefetch(Challenge.objects.filter(pk=c.pk)).get()
        r = ProgressEngine(user, as_of=date(2026, 1, 8)).evaluate(c)
        assert r.actual == 2 and r.expected == 3 and r.unit == "days"
        assert "05:30" in r.goal_description

    def test_api_requires_threshold(self, api):
        base = {"name": "Early", "start_date": "2026-01-05", "fields": [{"ref": "w", "label": "Wake", "field_type": "time"}],
                "goal": {"metric": "w", "period": "daily", "target": 1}}
        assert api.post("/api/challenges/", base, format="json").status_code == 400
        base["goal"].update({"time_comparison": "before", "time_threshold": "05:30"})
        r = api.post("/api/challenges/", base, format="json")
        assert r.status_code == 201 and r.json()["goal"]["time_threshold"] == "05:30:00"
        assert Goal.objects.get(challenge_id=r.json()["id"]).aggregation == "count"

    def test_early_riser_template_exists(self, api):
        slugs = [t["slug"] for t in api.get("/api/challenge-templates/").json()]
        assert "early-riser" in slugs


# ---------------------------------------------------------------------------- iCal
class TestICal:
    def test_export_and_feed(self, web, client, user, other_user):
        from apps.core.dates import user_today
        today = user_today(user)
        PlannedActivity.objects.create(user=user, title="Gym, legs; heavy", date=today, start_time=time(23), end_time=time(1))
        PlannedActivity.objects.create(user=other_user, title="Not mine", date=today, start_time=time(9), end_time=time(10))
        r = web.get(reverse("planner:export_ics"))
        body = r.content.decode()
        assert r["Content-Type"].startswith("text/calendar")
        assert body.startswith("BEGIN:VCALENDAR") and "SUMMARY:Gym\\, legs\\; heavy" in body and "Not mine" not in body
        assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
        token = user.profile.ensure_calendar_token()
        assert client.get(reverse("planner:feed", args=[token])).status_code == 200  # no login needed
        assert client.get(reverse("planner:feed", args=["wrong-token"])).status_code == 404
        web.post(reverse("planner:regenerate_feed"))
        assert client.get(reverse("planner:feed", args=[token])).status_code == 404

    def test_overnight_event_end(self, web, user):
        from apps.core.dates import user_today
        PlannedActivity.objects.create(user=user, title="Sleep", date=user_today(user), start_time=time(23), end_time=time(7))
        body = web.get(reverse("planner:export_ics")).content.decode()
        start = next(line for line in body.split("\r\n") if line.startswith("DTSTART"))
        end = next(line for line in body.split("\r\n") if line.startswith("DTEND"))
        assert end.split(":")[1] > start.split(":")[1]


# ---------------------------------------------------------------------------- Arabic / RTL
class TestArabic:
    def test_rtl_layout(self, web, user):
        user.profile.language = "ar"
        user.profile.save()
        html = web.get(reverse("dashboard:home")).content.decode()
        assert 'dir="rtl"' in html and 'lang="ar"' in html
        assert "rtl-flip" in html

    def test_language_switcher_on_login(self, client):
        html = client.get(reverse("accounts:login")).content.decode()
        assert 'value="ar"' in html and "العربية" in html

    def test_arabic_pdf(self, user):
        from django.utils import translation
        make_challenge(user, name="قراءة القرآن", start=date(2025, 1, 1))
        report = generate_monthly_report(user, 2025, 1)
        with translation.override("ar"):
            pdf = render_monthly_report_pdf(report)
        assert pdf[:4] == b"%PDF" and b"DejaVuSans" in pdf  # embedded Unicode font (subset)
        assert shape("قراءة") != "قراءة" and shape("Read") == "Read"
