"""Planner business operations."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.challenges.models import TrackingField
from apps.core.audit import audit
from apps.core.dates import daterange, minutes_between, user_now, user_today
from apps.core.models import AuditLog

from .models import MIDNIGHT, PlannedActivity, PlannerTemplate, PlannerTemplateItem, RecurringRule, validate_time_range

MAX_MATERIALISE_DAYS = 120
S = PlannedActivity.Status


# --- Recurrence ----------------------------------------------------------------------------
def ensure_occurrences(user, start: date, end: date) -> int:
    """Materialise occurrences of the user's active rules between start and end (inclusive).

    Idempotent: unique (rule, occurrence_date) + ignore_conflicts guarantees that a rule
    never produces duplicates, and occurrences that were edited/cancelled are kept.
    """
    if end < start:
        return 0
    end = min(end, start + timedelta(days=MAX_MATERIALISE_DAYS))
    rules = list(
        RecurringRule.objects.filter(user=user, is_active=True, start_date__lte=end).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=start)
        )
    )
    if not rules:
        return 0
    existing = set(
        PlannedActivity.objects.filter(user=user, recurring_rule__in=rules, occurrence_date__range=(start, end))
        .values_list("recurring_rule_id", "occurrence_date")
    )
    to_create = []
    for rule in rules:
        for day in daterange(max(start, rule.start_date), min(end, rule.end_date or end)):
            if (rule.pk, day) not in existing and rule.occurs_on(day):
                to_create.append(_activity_from_rule(rule, day))
    PlannedActivity.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create)


def _activity_from_rule(rule: RecurringRule, day: date) -> PlannedActivity:
    return PlannedActivity(
        user_id=rule.user_id, title=rule.title, description=rule.description, date=day,
        start_time=rule.start_time, end_time=rule.end_time, category_id=rule.category_id,
        challenge_id=rule.challenge_id, color=rule.color, priority=rule.priority, notes=rule.notes,
        recurring_rule=rule, occurrence_date=day,
    )


def _refresh_future_occurrences(rule: RecurringRule) -> None:
    """After a rule changes, drop future untouched occurrences; they are regenerated on read."""
    today = user_today(rule.user)
    PlannedActivity.objects.filter(
        recurring_rule=rule, date__gte=today, is_detached=False, status=S.PLANNED
    ).delete()


@transaction.atomic
def save_rule(rule: RecurringRule, *, created: bool) -> RecurringRule:
    rule.full_clean()
    rule.save()
    if not created:
        _refresh_future_occurrences(rule)
    audit(rule.user, AuditLog.Action.RULE_CHANGED, rule, created=created)
    return rule


@transaction.atomic
def delete_rule(rule: RecurringRule) -> None:
    _refresh_future_occurrences(rule)
    audit(rule.user, AuditLog.Action.RULE_CHANGED, rule, deleted=True)
    rule.delete()


# --- Activities ------------------------------------------------------------------------------
def find_overlaps(user, day: date, start: time, end: time, exclude_id: int | None = None) -> list[PlannedActivity]:
    """Activities of the same day whose time range intersects [start, end)."""
    s = start.hour * 60 + start.minute
    e = s + minutes_between(start, end)
    qs = PlannedActivity.objects.filter(user=user, date=day).exclude(status__in=[S.CANCELLED, S.RESCHEDULED])
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    result = []
    for a in qs:
        a_s = a.start_time.hour * 60 + a.start_time.minute
        a_e = a_s + a.duration_minutes
        if a_s < e and s < a_e:
            result.append(a)
    return result


def mark_detached(activity: PlannedActivity) -> None:
    if activity.recurring_rule_id:
        activity.is_detached = True


@transaction.atomic
def move_activity(activity: PlannedActivity, new_date: date, start: time, end: time) -> PlannedActivity:
    validate_time_range(start, end)
    activity.date, activity.start_time, activity.end_time = new_date, start, end
    mark_detached(activity)
    activity.save()
    audit(activity.user, AuditLog.Action.ACTIVITY_UPDATED, activity, moved_to=f"{new_date} {start:%H:%M}-{end:%H:%M}")
    return activity


@transaction.atomic
def duplicate_activity(activity: PlannedActivity, target_date: date | None = None) -> PlannedActivity:
    copy = PlannedActivity.objects.create(
        user=activity.user, title=activity.title, description=activity.description,
        date=target_date or activity.date, start_time=activity.start_time, end_time=activity.end_time,
        category=activity.category, challenge=activity.challenge, color=activity.color,
        priority=activity.priority, notes=activity.notes,
    )
    audit(activity.user, AuditLog.Action.ACTIVITY_CREATED, copy, duplicated_from=activity.pk)
    return copy


@transaction.atomic
def set_status(activity: PlannedActivity, status: str, *, actual_minutes: int | None = None, notes: str | None = None) -> PlannedActivity:
    """Status changes are always explicit user confirmations (planning != succeeding)."""
    if status not in S.values:
        raise ValidationError({"status": _("Unknown status.")})
    if status == S.RESCHEDULED:
        raise ValidationError({"status": _("Use the reschedule action to choose a new time.")})
    old = activity.status
    activity.status = status
    if status in PlannedActivity.DONE_STATUSES:
        activity.completed_at = timezone.now()
        if actual_minutes is not None:
            if actual_minutes < 0 or actual_minutes > 24 * 60:
                raise ValidationError({"actual_minutes": _("Enter a duration between 0 and 24 hours.")})
            activity.actual_minutes = actual_minutes
        elif activity.actual_minutes is None and status == S.COMPLETED:
            activity.actual_minutes = activity.duration_minutes
    else:
        activity.completed_at = None
    if notes is not None:
        activity.notes = notes[:2000]
    mark_detached(activity)
    activity.save()
    audit(activity.user, AuditLog.Action.ACTIVITY_STATUS, activity, old=old, new=status)
    return activity


@transaction.atomic
def reschedule_activity(activity: PlannedActivity, new_date: date, start: time | None = None, end: time | None = None) -> PlannedActivity:
    start = start or activity.start_time
    end = end or activity.end_time
    validate_time_range(start, end)
    new = PlannedActivity.objects.create(
        user=activity.user, title=activity.title, description=activity.description, date=new_date,
        start_time=start, end_time=end, category=activity.category, challenge=activity.challenge,
        color=activity.color, priority=activity.priority, notes=activity.notes, rescheduled_from=activity,
    )
    activity.status = S.RESCHEDULED
    mark_detached(activity)
    activity.save()
    audit(activity.user, AuditLog.Action.ACTIVITY_STATUS, activity, new="rescheduled", to=new.pk)
    return new


@transaction.atomic
def delete_activity(activity: PlannedActivity) -> None:
    """A recurring occurrence is cancelled (so the rule does not recreate it);
    a one-off activity is deleted."""
    audit(activity.user, AuditLog.Action.ACTIVITY_DELETED, activity)
    if activity.recurring_rule_id:
        activity.status = S.CANCELLED
        activity.is_detached = True
        activity.save()
    else:
        activity.delete()


def entry_suggestion(activity: PlannedActivity) -> dict | None:
    """Pre-filled values to record a linked challenge entry. Never saved automatically:
    the user reviews and confirms them."""
    challenge = activity.challenge
    if challenge is None:
        return None
    minutes = activity.actual_minutes if activity.actual_minutes is not None else activity.duration_minutes
    values = {}
    haystack = f"{activity.title} {activity.category.name if activity.category else ''}".lower()
    for f in challenge.fields.filter(is_active=True):
        T = TrackingField.FieldType
        if f.field_type == T.DURATION:
            values[f.key] = minutes
        elif f.field_type == T.BOOLEAN:
            values[f.key] = True
        elif f.field_type == T.DECIMAL and f.unit.lower() in {"h", "hour", "hours", "heures"}:
            values[f.key] = round(minutes / 60, 2)
        elif f.field_type == T.SELECT:
            match = next((o for o in f.options if str(o).lower() in haystack), None)
            if match:
                values[f.key] = match
    return {
        "challenge_id": challenge.pk,
        "challenge_name": challenge.name,
        "date": activity.date.isoformat(),
        "values": values,
        "note": activity.notes,
        "planned_activity": activity.pk,
    }


# --- Templates -------------------------------------------------------------------------------
@transaction.atomic
def apply_template(template: PlannerTemplate, dates: list[date], replace: bool = False) -> list[PlannedActivity]:
    if not dates:
        raise ValidationError({"dates": _("Choose at least one day.")})
    if len(dates) > 62:
        raise ValidationError({"dates": _("You can apply a template to at most 62 days at once.")})
    items = list(template.items.all())
    created = []
    for day in sorted(set(dates)):
        if replace:
            PlannedActivity.objects.filter(user=template.user, date=day, recurring_rule__isnull=True, status=S.PLANNED).delete()
            PlannedActivity.objects.filter(user=template.user, date=day, recurring_rule__isnull=False, status=S.PLANNED).update(
                status=S.CANCELLED, is_detached=True
            )
        for item in items:
            created.append(PlannedActivity(
                user=template.user, title=item.title, date=day, start_time=item.start_time, end_time=item.end_time,
                category=item.category, challenge=item.challenge, color=item.color, priority=item.priority, notes=item.notes,
            ))
    PlannedActivity.objects.bulk_create(created)
    audit(template.user, AuditLog.Action.TEMPLATE_APPLIED, template, dates=[d.isoformat() for d in dates], replace=replace)
    return created


@transaction.atomic
def template_from_day(user, day: date, name: str, description: str = "") -> PlannerTemplate:
    activities = PlannedActivity.objects.filter(user=user, date=day).exclude(status__in=[S.CANCELLED, S.RESCHEDULED])
    if not activities.exists():
        raise ValidationError({"date": _("This day has no activities to save.")})
    if PlannerTemplate.objects.filter(user=user, name=name).exists():
        raise ValidationError({"name": _("You already have a template with this name.")})
    template = PlannerTemplate.objects.create(user=user, name=name, description=description)
    PlannerTemplateItem.objects.bulk_create([
        PlannerTemplateItem(template=template, title=a.title, start_time=a.start_time, end_time=a.end_time,
                            category=a.category, challenge=a.challenge, color=a.color, priority=a.priority, notes=a.notes)
        for a in activities
    ])
    return template


# --- Summaries -----------------------------------------------------------------------------
def is_overdue(activity: PlannedActivity, now: datetime) -> bool:
    if activity.status not in (S.PLANNED, S.IN_PROGRESS):
        return False
    end_day = activity.date + timedelta(days=1) if activity.end_time == MIDNIGHT else activity.date
    end_dt = datetime.combine(end_day, activity.end_time)
    return end_dt <= now.replace(tzinfo=None)


def summarize(activities, user) -> dict:
    """Counts used by dashboard/today/reports. 'missed' = explicitly missed + overdue unconfirmed."""
    now = user_now(user)
    items = [a for a in activities if a.status not in (S.CANCELLED, S.RESCHEDULED)]
    completed = sum(1 for a in items if a.status == S.COMPLETED)
    partial = sum(1 for a in items if a.status == S.PARTIALLY_COMPLETED)
    missed = sum(1 for a in items if a.status == S.MISSED or is_overdue(a, now))
    remaining = len(items) - completed - partial - missed
    planned_minutes = sum(a.duration_minutes for a in items)
    done_minutes = sum((a.actual_minutes or a.duration_minutes) for a in items if a.is_done)
    total = len(items)
    return {
        "planned": total,
        "completed": completed,
        "partial": partial,
        "missed": missed,
        "remaining": max(remaining, 0),
        "planned_minutes": planned_minutes,
        "done_minutes": done_minutes,
        "completion_rate": round((completed + 0.5 * partial) / total * 100, 1) if total else None,
    }
