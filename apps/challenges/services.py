"""Challenge business operations. Views/APIs call these; they never write models directly."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils.text import slugify

from apps.core.audit import audit
from apps.core.dates import user_today
from apps.core.models import AuditLog

from .models import Challenge, ChallengePause, Goal, Milestone, RestDay, Schedule, TrackingField


def unique_field_key(label: str, taken: set[str]) -> str:
    base = (slugify(label) or "field").replace("-", "_")[:36]
    key, i = base, 2
    while key in taken:
        key = f"{base}_{i}"
        i += 1
    taken.add(key)
    return key


@transaction.atomic
def create_challenge(user, data: dict) -> Challenge:
    """`data` is the validated wizard payload (see serializers.ChallengeCreateSerializer)."""
    challenge = Challenge.objects.create(
        user=user,
        name=data["name"],
        description=data.get("description", ""),
        category=data.get("category"),
        template=data.get("template"),
        icon=data.get("icon") or "target",
        color=data.get("color") or "indigo",
        start_date=data["start_date"],
        end_date=data.get("end_date"),
    )
    keys: set[str] = set()
    fields_by_ref: dict[str, TrackingField] = {}
    for order, f in enumerate(data.get("fields", [])):
        field = TrackingField.objects.create(
            challenge=challenge,
            key=unique_field_key(f.get("key") or f["label"], keys),
            label=f["label"],
            field_type=f["field_type"],
            unit=f.get("unit", ""),
            options=f.get("options") or [],
            required=f.get("required", False),
            min_value=f.get("min_value"),
            max_value=f.get("max_value"),
            order=order,
        )
        fields_by_ref[f.get("ref") or f["label"]] = field
        fields_by_ref[field.key] = field

    goal_data = data["goal"]
    metric_ref = goal_data.get("metric")
    Goal.objects.create(
        challenge=challenge,
        metric=fields_by_ref.get(metric_ref) if metric_ref else None,
        period=goal_data["period"],
        aggregation=goal_data.get("aggregation", Goal.Aggregation.SUM),
        target=goal_data["target"],
        min_per_entry=goal_data.get("min_per_entry"),
        time_comparison=goal_data.get("time_comparison") or "",
        time_threshold=goal_data.get("time_threshold"),
        effective_from=challenge.start_date,
    )
    sched = data.get("schedule") or {}
    Schedule.objects.create(
        challenge=challenge,
        frequency=sched.get("frequency", Schedule.Frequency.DAILY),
        weekdays=sorted(set(sched.get("weekdays") or [])),
        interval_days=sched.get("interval_days") or 1,
        effective_from=challenge.start_date,
    )
    for m in data.get("milestones", []):
        Milestone.objects.create(challenge=challenge, title=m["title"], target_value=m["target_value"])

    audit(user, AuditLog.Action.CHALLENGE_CREATED, challenge)
    return challenge


def _version_change(challenge: Challenge, model, current, values: dict, effective_from: date):
    """Close `current` and open a new version from `effective_from`, unless the
    current version starts on/after that date (nothing to preserve: edit in place)."""
    if current is None:
        return model.objects.create(challenge=challenge, effective_from=effective_from, **values)
    if current.effective_from >= effective_from:
        for k, v in values.items():
            setattr(current, k, v)
        current.full_clean()
        current.save()
        return current
    current.effective_to = effective_from - timedelta(days=1)
    current.save(update_fields=["effective_to", "updated_at"])
    new = model(challenge=challenge, effective_from=effective_from, **values)
    new.full_clean()
    new.save()
    return new


def _effective_date(challenge: Challenge, user) -> date:
    return max(user_today(user), challenge.start_date)


@transaction.atomic
def update_goal(challenge: Challenge, values: dict, effective_from: date | None = None) -> Goal:
    effective_from = effective_from or _effective_date(challenge, challenge.user)
    current = Goal.objects.select_for_update().filter(challenge=challenge, effective_to__isnull=True).first()
    if current is not None and _same(current, values):
        return current
    goal = _version_change(challenge, Goal, current, values, effective_from)
    audit(challenge.user, AuditLog.Action.GOAL_CHANGED, challenge, effective_from=effective_from, **{k: v.pk if hasattr(v, "pk") else v for k, v in values.items()})
    return goal


@transaction.atomic
def update_schedule(challenge: Challenge, values: dict, effective_from: date | None = None) -> Schedule:
    effective_from = effective_from or _effective_date(challenge, challenge.user)
    values = {**values, "weekdays": sorted(set(values.get("weekdays") or []))}
    current = Schedule.objects.select_for_update().filter(challenge=challenge, effective_to__isnull=True).first()
    if current is not None and _same(current, values):
        return current
    schedule = _version_change(challenge, Schedule, current, values, effective_from)
    audit(challenge.user, AuditLog.Action.SCHEDULE_CHANGED, challenge, effective_from=effective_from, **values)
    return schedule


def _same(obj, values: dict) -> bool:
    for k, v in values.items():
        current = getattr(obj, k)
        if isinstance(current, Decimal) or isinstance(v, Decimal):
            if (current is None) != (v is None) or (current is not None and Decimal(str(current)) != Decimal(str(v))):
                return False
        elif current != v:
            return False
    return True


@transaction.atomic
def change_status(challenge: Challenge, new_status: str) -> Challenge:
    """Status transitions with their side effects:
    * PAUSED   -> opens a pause period starting today (excluded from evaluation)
    * ACTIVE   -> closes any open pause; clears early-closing date
    * COMPLETED / ARCHIVED -> records `closed_on` when closed before the end date
    """
    today = user_today(challenge.user)
    old = challenge.status
    if new_status == old:
        return challenge
    open_pause = challenge.pauses.filter(end_date__isnull=True).first()

    if new_status == Challenge.Status.PAUSED:
        if open_pause is None:
            ChallengePause.objects.create(challenge=challenge, start_date=max(today, challenge.start_date))
    elif open_pause is not None:
        if open_pause.start_date >= today:
            open_pause.delete()
        else:
            open_pause.end_date = today - timedelta(days=1)
            open_pause.save(update_fields=["end_date", "updated_at"])

    if new_status in (Challenge.Status.COMPLETED, Challenge.Status.ARCHIVED):
        if challenge.closed_on is None and (challenge.end_date is None or today < challenge.end_date) and old != Challenge.Status.COMPLETED:
            challenge.closed_on = max(today, challenge.start_date)
    elif new_status == Challenge.Status.ACTIVE:
        challenge.closed_on = None

    challenge.status = new_status
    challenge.save(update_fields=["status", "closed_on", "updated_at"])
    audit(challenge.user, AuditLog.Action.CHALLENGE_STATUS, challenge, old=old, new=new_status)
    return challenge


def toggle_rest_day(user, day: date, challenge: Challenge | None = None) -> bool:
    """Mark/unmark a planned rest day. Returns True if the day is now a rest day."""
    existing = RestDay.objects.filter(user=user, date=day, challenge=challenge).first()
    if existing:
        existing.delete()
        return False
    RestDay.objects.create(user=user, date=day, challenge=challenge)
    return True


def challenge_definition(challenge: Challenge) -> dict:
    """Serialisable wizard payload of an existing challenge (used for templates/duplication)."""
    goal = challenge.current_goal
    schedule = challenge.current_schedule
    return {
        "fields": [
            {
                "label": f.label, "key": f.key, "field_type": f.field_type, "unit": f.unit,
                "options": f.options, "required": f.required,
                "min_value": float(f.min_value) if f.min_value is not None else None,
                "max_value": float(f.max_value) if f.max_value is not None else None,
            }
            for f in challenge.active_fields
        ],
        "goal": {
            "metric": goal.metric.key if goal and goal.metric else None,
            "period": goal.period if goal else Goal.Period.DAILY,
            "aggregation": goal.aggregation if goal else Goal.Aggregation.COUNT,
            "target": float(goal.target) if goal else 1,
            "min_per_entry": float(goal.min_per_entry) if goal and goal.min_per_entry is not None else None,
            "time_comparison": goal.time_comparison if goal else "",
            "time_threshold": goal.time_threshold.strftime("%H:%M") if goal and goal.time_threshold else None,
        },
        "schedule": {
            "frequency": schedule.frequency if schedule else Schedule.Frequency.DAILY,
            "weekdays": schedule.weekdays if schedule else [],
            "interval_days": schedule.interval_days if schedule else 1,
        },
    }
