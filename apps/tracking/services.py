"""Entry recording with strict server-side validation of every typed value."""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from apps.challenges.models import Challenge, TrackingField
from apps.core.audit import audit
from apps.core.dates import user_today
from apps.core.models import AuditLog

from .models import ChallengeEntry, EntryFieldValue

T = TrackingField.FieldType
MAX_NUMBER = Decimal("99999999")


def parse_value(field: TrackingField, raw):
    """Return the kwargs for EntryFieldValue, or None when the value is empty."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None
    ft = field.field_type
    if ft == T.BOOLEAN:
        if isinstance(raw, bool):
            return {"value_bool": raw}
        text = str(raw).strip().lower()
        if text in {"true", "1", "yes", "on", "done"}:
            return {"value_bool": True}
        if text in {"false", "0", "no", "off"}:
            return {"value_bool": False}
        raise ValidationError(_("Choose done or not done."))
    if ft in (T.INTEGER, T.DECIMAL, T.DURATION):
        if isinstance(raw, bool):
            raise ValidationError(_("Enter a number."))
        try:
            number = Decimal(str(raw).replace(",", ".").strip())
        except (InvalidOperation, ValueError):
            raise ValidationError(_("Enter a number."))
        if not number.is_finite():
            raise ValidationError(_("Enter a number."))
        if ft in (T.INTEGER, T.DURATION) and number != number.to_integral_value():
            raise ValidationError(_("Enter a whole number."))
        if number < 0:
            raise ValidationError(_("The value cannot be negative."))
        if number > MAX_NUMBER:
            raise ValidationError(_("This value is too large."))
        if field.min_value is not None and number < field.min_value:
            raise ValidationError(_("Minimum is %(v)s.") % {"v": field.min_value})
        if field.max_value is not None and number > field.max_value:
            raise ValidationError(_("Maximum is %(v)s.") % {"v": field.max_value})
        return {"value_number": number.quantize(Decimal("0.001"))}
    if ft == T.TIME:
        if isinstance(raw, time):
            return {"value_time": raw}
        try:
            return {"value_time": time.fromisoformat(str(raw).strip()[:5])}
        except ValueError:
            raise ValidationError(_("Enter a valid time (HH:MM)."))
    text = str(raw).strip()
    if ft == T.SELECT:
        if text not in [str(o) for o in field.options]:
            raise ValidationError(_("Select a valid option."))
    if len(text) > 500:
        raise ValidationError(_("Keep it under 500 characters."))
    return {"value_text": text}


def validate_entry(challenge: Challenge, entry_date: date, raw_values: dict, user) -> list[tuple[TrackingField, dict | None]]:
    errors: dict[str, list[str]] = {}
    today = user_today(user)
    if entry_date > today:
        errors["date"] = [_("You can't record results in the future.")]
    elif entry_date < challenge.start_date:
        errors["date"] = [_("This date is before the challenge starts.")]
    elif challenge.end_date and entry_date > challenge.end_date:
        errors["date"] = [_("This date is after the challenge ends.")]

    fields = [f for f in challenge.fields.all() if f.is_active]
    by_ref = {}
    for f in fields:
        by_ref[str(f.pk)] = f
        by_ref[f.key] = f
    unknown = [k for k in raw_values if str(k) not in by_ref]
    if unknown:
        errors["values"] = [_("Unknown field(s): %(f)s") % {"f": ", ".join(map(str, unknown))}]

    parsed: list[tuple[TrackingField, dict | None]] = []
    supplied = {by_ref[str(k)].pk: v for k, v in raw_values.items() if str(k) in by_ref}
    for f in fields:
        raw = supplied.get(f.pk)
        try:
            value = parse_value(f, raw)
        except ValidationError as exc:
            errors[f.key] = exc.messages
            continue
        if value is None and f.required:
            errors[f.key] = [_("This field is required.")]
            continue
        if f.pk in supplied:
            parsed.append((f, value))
    if not any(v is not None for _field, v in parsed) and not errors:
        errors["values"] = [_("Fill in at least one value.")]
    if errors:
        raise ValidationError(errors)
    return parsed


@transaction.atomic
def create_entry(user, challenge: Challenge, entry_date: date, raw_values: dict, note: str = "",
                 source: str = ChallengeEntry.Source.MANUAL, planned_activity=None) -> ChallengeEntry:
    if challenge.user_id != user.pk:
        raise ValidationError(_("Challenge not found."))
    parsed = validate_entry(challenge, entry_date, raw_values, user)
    entry = ChallengeEntry.objects.create(
        user=user, challenge=challenge, date=entry_date, note=(note or "")[:2000],
        source=source, planned_activity=planned_activity,
    )
    EntryFieldValue.objects.bulk_create(
        [EntryFieldValue(entry=entry, field=f, **v) for f, v in parsed if v is not None]
    )
    audit(user, AuditLog.Action.ENTRY_CREATED, entry, challenge=challenge.pk, date=entry_date)
    return entry


@transaction.atomic
def update_entry(entry: ChallengeEntry, entry_date: date, raw_values: dict, note: str | None = None) -> ChallengeEntry:
    challenge = entry.challenge
    parsed = validate_entry(challenge, entry_date, raw_values, entry.user)
    entry.date = entry_date
    if note is not None:
        entry.note = note[:2000]
    entry.save()
    for f, v in parsed:
        if v is None:
            EntryFieldValue.objects.filter(entry=entry, field=f).delete()
        else:
            defaults = {"value_number": None, "value_bool": None, "value_time": None, "value_text": "", **v}
            EntryFieldValue.objects.update_or_create(entry=entry, field=f, defaults=defaults)
    audit(entry.user, AuditLog.Action.ENTRY_UPDATED, entry, challenge=challenge.pk, date=entry_date)
    return entry


def delete_entry(entry: ChallengeEntry) -> None:
    audit(entry.user, AuditLog.Action.ENTRY_DELETED, entry, challenge=entry.challenge_id, date=entry.date)
    entry.delete()


def entry_values_dict(entry: ChallengeEntry) -> dict:
    return {v.field.key: v.value for v in entry.values.all()}
