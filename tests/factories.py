"""Small explicit test helpers (no external factory library needed)."""
from __future__ import annotations

import itertools
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.challenges.models import Challenge
from apps.challenges.services import create_challenge
from apps.tracking.models import ChallengeEntry, EntryFieldValue

_seq = itertools.count(1)


def make_user(username: str | None = None, password: str = "Str0ng-pass!", tz: str = "UTC", **extra):
    n = next(_seq)
    username = username or f"user{n}"
    user = get_user_model().objects.create_user(username=username, email=f"{username}@example.com", password=password, **extra)
    user.profile.timezone = tz
    user.profile.save()
    return user


def make_challenge(user, *, name="Challenge", start=date(2025, 1, 6), end=None, fields=None, goal=None, schedule=None, milestones=None) -> Challenge:
    fields = fields if fields is not None else [{"label": "Amount", "key": "amount", "field_type": "integer", "unit": "pages"}]
    goal = goal or {"metric": "amount", "period": "daily", "aggregation": "sum", "target": Decimal("2")}
    schedule = schedule or {"frequency": "daily", "weekdays": [], "interval_days": 1}
    challenge = create_challenge(user, {
        "name": name, "start_date": start, "end_date": end, "fields": fields,
        "goal": goal, "schedule": schedule, "milestones": milestones or [],
    })
    return Challenge.objects.get(pk=challenge.pk)


def add_entry(challenge: Challenge, day: date, **values) -> ChallengeEntry:
    """Direct ORM insert (bypasses 'not in the future' validation for engine tests)."""
    entry = ChallengeEntry.objects.create(user=challenge.user, challenge=challenge, date=day)
    fields = {f.key: f for f in challenge.fields.all()}
    for key, value in values.items():
        field = fields[key]
        if isinstance(value, bool):
            EntryFieldValue.objects.create(entry=entry, field=field, value_bool=value)
        else:
            EntryFieldValue.objects.create(entry=entry, field=field, value_number=Decimal(str(value)))
    return entry


def session_entry(challenge: Challenge, day: date) -> ChallengeEntry:
    return ChallengeEntry.objects.create(user=challenge.user, challenge=challenge, date=day)
