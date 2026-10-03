"""Create a demo account with realistic data.

    python manage.py seed_demo            # creates user "demo" (password: LifeFlow-demo1)
    python manage.py seed_demo --reset    # deletes demo users first

Demo users are flagged `is_demo=True` and can be removed at any time with --reset;
real accounts are never touched.
"""
import random
from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.challenges.models import ChallengeCategory, RestDay
from apps.challenges.services import create_challenge
from apps.core.dates import user_today
from apps.journal.models import JournalEntry, WeeklyReview
from apps.planner import services as planner
from apps.planner.models import ActivityCategory, PlannedActivity, PlannerTemplate, PlannerTemplateItem, RecurringRule
from apps.reports.services.monthly import generate_monthly_report
from apps.tracking.models import ChallengeEntry, EntryFieldValue

PASSWORD = "LifeFlow-demo1"


class Command(BaseCommand):
    help = "Seed a demo user with challenges, entries, planner and reports."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo users first.")
        parser.add_argument("--days", type=int, default=50)

    def handle(self, *args, **opts):
        User = get_user_model()
        if opts["reset"]:
            n, _ = User.objects.filter(is_demo=True).delete()
            self.stdout.write(f"Removed demo data ({n} rows).")
        if User.objects.filter(username="demo").exists():
            self.stdout.write(self.style.WARNING("User 'demo' already exists. Use --reset to recreate it."))
            return
        with transaction.atomic():
            user = self._seed("demo", "demo@lifeflow.local", "Yassine", opts["days"], seed=42)
            self._seed("demo2", "demo2@lifeflow.local", "Sara", 20, seed=7, light=True)
        self.stdout.write(self.style.SUCCESS(f"Demo ready → username: demo / password: {PASSWORD} (also demo2)"))
        return None if user else None

    # ------------------------------------------------------------------------------------
    def _seed(self, username, email, first_name, days, seed, light=False):
        rnd = random.Random(seed)
        User = get_user_model()
        user = User.objects.create_user(username=username, email=email, password=PASSWORD, first_name=first_name, is_demo=True)
        profile = user.profile
        profile.timezone = "Africa/Casablanca"
        profile.onboarding_completed = True
        profile.save()
        today = user_today(user)
        start = today - timedelta(days=days)
        cats = {c.name: c for c in ChallengeCategory.objects.filter(user=user)}

        defs = [
            dict(name="Sport", icon="dumbbell", color="rose", category=cats["Health & Fitness"], end=None,
                 fields=[{"label": "Activity type", "key": "type", "field_type": "select", "options": ["Gym", "Football", "Running"]},
                         {"label": "Duration", "key": "duration", "field_type": "duration"}],
                 goal={"metric": None, "period": "daily", "aggregation": "count", "target": Decimal(1)},
                 schedule={"frequency": "weekdays", "weekdays": [0, 1, 2, 3, 4, 5]}, rate=0.78),
            dict(name="Qur'an", icon="book-marked", color="emerald", category=cats["Spiritual"], end=None,
                 fields=[{"label": "Pages", "key": "pages", "field_type": "integer", "unit": "pages", "required": True},
                         {"label": "Surah", "key": "surah", "field_type": "text"}],
                 goal={"metric": "pages", "period": "daily", "aggregation": "sum", "target": Decimal(2)},
                 schedule={"frequency": "daily"}, rate=0.9),
            dict(name="Learning", icon="graduation-cap", color="indigo", category=cats["Learning"], end=today + timedelta(days=40),
                 fields=[{"label": "Duration", "key": "duration", "field_type": "duration", "required": True},
                         {"label": "Subject", "key": "subject", "field_type": "text"}],
                 goal={"metric": "duration", "period": "daily", "aggregation": "sum", "target": Decimal(120)},
                 schedule={"frequency": "weekdays", "weekdays": [0, 1, 2, 3, 4]}, rate=0.65),
            dict(name="Fajr", icon="sunrise", color="teal", category=cats["Spiritual"], end=None,
                 fields=[{"label": "Prayed on time", "key": "done", "field_type": "boolean", "required": True},
                         {"label": "Wake-up time", "key": "wake_up", "field_type": "time"}],
                 goal={"metric": "done", "period": "daily", "aggregation": "count", "target": Decimal(1)},
                 schedule={"frequency": "daily"}, rate=0.88),
            dict(name="Running", icon="footprints", color="orange", category=cats["Health & Fitness"], end=today + timedelta(days=30),
                 fields=[{"label": "Duration", "key": "duration", "field_type": "duration"},
                         {"label": "Distance", "key": "distance", "field_type": "decimal", "unit": "km"}],
                 goal={"metric": "duration", "period": "weekly", "aggregation": "count", "target": Decimal(3), "min_per_entry": Decimal(30)},
                 schedule={"frequency": "daily"}, rate=0.4),
            dict(name="Reading", icon="book-open", color="violet", category=cats["Learning"], end=None,
                 fields=[{"label": "Pages", "key": "pages", "field_type": "integer", "unit": "pages"}],
                 goal={"metric": "pages", "period": "weekly", "aggregation": "sum", "target": Decimal(20)},
                 schedule={"frequency": "daily"}, rate=0.35),
            dict(name="Water", icon="glass-water", color="sky", category=cats["Wellness"], end=None,
                 fields=[{"label": "Water", "key": "water", "field_type": "decimal", "unit": "L"}],
                 goal={"metric": "water", "period": "daily", "aggregation": "sum", "target": Decimal(2)},
                 schedule={"frequency": "daily"}, rate=0.7),
        ]
        if light:
            defs = defs[1:3]
        challenges = {}
        for d in defs:
            c = create_challenge(user, {
                "name": d["name"], "icon": d["icon"], "color": d["color"], "category": d["category"],
                "start_date": start, "end_date": d["end"], "fields": d["fields"], "goal": d["goal"],
                "schedule": d["schedule"], "milestones": [],
            })
            challenges[d["name"]] = (c, d)
        if "Learning" in challenges:
            c = challenges["Learning"][0]
            for title, target in (("10 h", 600), ("50 h", 3000), ("100 h", 6000)):
                c.milestones.create(title=title, target_value=target)

        # Entries
        for name, (c, d) in challenges.items():
            fields = {f.key: f for f in c.fields.all()}
            for i in range(days + 1):
                day = start + timedelta(days=i)
                if day == today and rnd.random() < 0.5:
                    continue
                sched = d["schedule"]
                if sched["frequency"] == "weekdays" and day.weekday() not in sched["weekdays"]:
                    continue
                if rnd.random() > d["rate"]:
                    continue
                entry = ChallengeEntry.objects.create(user=user, challenge=c, date=day, source="manual")
                vals = []
                if name == "Sport":
                    vals += [EntryFieldValue(entry=entry, field=fields["type"], value_text=rnd.choice(["Gym", "Gym", "Football", "Running"])),
                             EntryFieldValue(entry=entry, field=fields["duration"], value_number=rnd.choice([45, 60, 75, 90]))]
                elif name in ("Qur'an",):
                    vals += [EntryFieldValue(entry=entry, field=fields["pages"], value_number=rnd.choice([1, 2, 2, 2, 3, 4]))]
                elif name == "Learning":
                    vals += [EntryFieldValue(entry=entry, field=fields["duration"], value_number=rnd.choice([60, 90, 120, 120, 150, 180])),
                             EntryFieldValue(entry=entry, field=fields["subject"], value_text=rnd.choice(["Django", "Algorithms", "English", "SQL"]))]
                elif name == "Fajr":
                    ok = rnd.random() < 0.92
                    vals += [EntryFieldValue(entry=entry, field=fields["done"], value_bool=ok),
                             EntryFieldValue(entry=entry, field=fields["wake_up"], value_time=time(5, rnd.choice([0, 5, 10, 15, 20, 30])))]
                elif name == "Running":
                    vals += [EntryFieldValue(entry=entry, field=fields["duration"], value_number=rnd.choice([25, 35, 40, 45])),
                             EntryFieldValue(entry=entry, field=fields["distance"], value_number=Decimal(str(round(rnd.uniform(4, 9), 1))))]
                elif name == "Reading":
                    vals += [EntryFieldValue(entry=entry, field=fields["pages"], value_number=rnd.choice([5, 8, 10, 12]))]
                elif name == "Water":
                    vals += [EntryFieldValue(entry=entry, field=fields["water"], value_number=Decimal(str(rnd.choice([1.5, 2, 2, 2.5]))))]
                EntryFieldValue.objects.bulk_create(vals)

        RestDay.objects.create(user=user, challenge=None, date=today - timedelta(days=9), note="Family day")
        if light:
            return user

        # Planner routines
        acats = {c.name: c for c in ActivityCategory.objects.filter(user=user)}
        sport = challenges["Sport"][0]
        learning = challenges["Learning"][0]
        quran = challenges["Qur'an"][0]
        rules = [
            ("Fajr + Qur'an", time(5, 0), time(5, 30), "daily", [], acats["Qur'an"], quran),
            ("Breakfast", time(8, 30), time(9, 0), "daily", [], acats["Food"], None),
            ("Gym", time(9, 0), time(10, 30), "weekly", [0, 2, 4], acats["Sport"], sport),
            ("Football", time(17, 0), time(18, 30), "weekly", [5], acats["Sport"], sport),
            ("Work", time(10, 30), time(13, 0), "weekly", [0, 1, 2, 3, 4], acats["Work"], None),
            ("Lunch", time(13, 0), time(14, 0), "daily", [], acats["Food"], None),
            ("University", time(14, 0), time(18, 0), "weekly", [1, 3], acats["Study"], None),
            ("Learning", time(19, 0), time(21, 0), "weekly", [0, 1, 2, 3, 4], acats["Study"], learning),
            ("Sleep", time(23, 0), time(0, 0), "daily", [], acats["Sleep"], None),
        ]
        for title, s, e, freq, wd, cat, ch in rules:
            RecurringRule.objects.create(user=user, title=title, start_time=s, end_time=e, frequency=freq, weekdays=wd,
                                         start_date=today - timedelta(days=21), category=cat, challenge=ch)
        planner.ensure_occurrences(user, today - timedelta(days=21), today + timedelta(days=7))
        now = timezone.now()
        for a in PlannedActivity.objects.filter(user=user, date__lt=today):
            r = rnd.random()
            a.status = "completed" if r < 0.72 else ("partial" if r < 0.82 else "missed")
            a.is_detached = True
            if a.status != "missed":
                a.completed_at = now
                a.actual_minutes = a.duration_minutes
            a.save()
        for a in PlannedActivity.objects.filter(user=user, date=today, end_time__lte=time(9, 0)).exclude(end_time=time(0, 0)):
            a.status, a.completed_at, a.is_detached = "completed", now, True
            a.save()
        PlannedActivity.objects.create(user=user, title="Dentist", date=today + timedelta(days=2), start_time=time(16, 0),
                                       end_time=time(16, 45), category=acats["Personal"], priority="high")

        tpl = PlannerTemplate.objects.create(user=user, name="University Day", icon="graduation-cap", color="indigo")
        for title, s, e, cat in [("Fajr + Qur'an", time(5), time(5, 30), "Qur'an"), ("Sleep", time(5, 30), time(8, 0), "Sleep"),
                                 ("University", time(8, 30), time(12, 0), "Study"), ("Lunch", time(12, 0), time(13, 0), "Food"),
                                 ("University", time(14), time(18), "Study"), ("Return", time(18), time(19), "Travel"),
                                 ("Learning", time(19), time(21), "Study"), ("Sleep", time(23), time(0), "Sleep")]:
            PlannerTemplateItem.objects.create(template=tpl, title=title, start_time=s, end_time=e, category=acats[cat])
        tpl2 = PlannerTemplate.objects.create(user=user, name="Weekend", icon="sun", color="amber")
        for title, s, e, cat in [("Fajr + Qur'an", time(5), time(5, 30), "Qur'an"), ("Family breakfast", time(9), time(10), "Family"),
                                 ("Football", time(17), time(18, 30), "Sport"), ("Rest", time(20), time(22), "Rest")]:
            PlannerTemplateItem.objects.create(template=tpl2, title=title, start_time=s, end_time=e, category=acats[cat])

        # Journal & review
        JournalEntry.objects.create(user=user, date=today - timedelta(days=1), title="Good momentum", mood=4,
                                    content="Gym in the morning and two solid hours of Django in the evening. Keep going.")
        JournalEntry.objects.create(user=user, date=today - timedelta(days=4), title="Tired day", mood=2, challenge=learning, scope="challenge",
                                    content="Skipped the learning block — too tired after university. Plan an earlier slot on Tuesdays.")
        WeeklyReview.objects.create(user=user, week_start=today - timedelta(days=today.weekday() + 7),
                                    went_well="Consistent Fajr and Qur'an.", difficult="Running sessions were too short.",
                                    improve="Schedule running on Saturday morning.", rating=4)

        # Report for the previous month
        prev = today.replace(day=1) - timedelta(days=1)
        if prev >= start:
            generate_monthly_report(user, prev.year, prev.month)
        return user
