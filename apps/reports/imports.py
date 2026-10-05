"""CSV import of challenge entries — the format produced by the CSV export:

    Challenge,Date,<field label or key>…,Note[,Source]

* the challenge is matched by name (case-insensitive) among the user's challenges;
* columns are matched to that challenge's fields by label or key; unknown columns are ignored;
* every row goes through the normal entry validation (types, required fields, dates);
* rows identical to an existing entry (same challenge, date, values and note) are skipped,
  so re-importing a file is safe.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from apps.challenges.models import Challenge
from apps.core.dates import parse_date
from apps.tracking.models import ChallengeEntry
from apps.tracking.services import create_entry, entry_values_dict

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
RESERVED = {"challenge", "date", "note", "source"}
TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")


@dataclass
class ImportReport:
    created: int = 0
    skipped: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.errors)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValidationError(_("The file encoding is not supported (use UTF-8)."))


def _normalise_value(value: str) -> str:
    """Strip whitespace and undo the export's formula-injection guard ('=…, '-…)."""
    value = value.strip()
    if value[:1] == "'" and value[1:2] in ("=", "+", "-", "@"):
        value = value[1:]
    return value


def import_entries_csv(user, uploaded) -> ImportReport:
    raw = uploaded.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValidationError(_("The file is too large (2 MB maximum)."))
    text = _decode(raw)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [h.strip() for h in (reader.fieldnames or [])]
    lower = {h.lower(): h for h in headers}
    if "challenge" not in lower or "date" not in lower:
        raise ValidationError(_("The file must contain the columns “Challenge” and “Date” (export a CSV first to see the format)."))

    challenges = {c.name.strip().lower(): c for c in Challenge.objects.filter(user=user).prefetch_related("fields")}
    report = ImportReport()
    for line, row in enumerate(reader, start=2):
        if line - 1 > MAX_ROWS:
            report.errors.append((line, _("Stopped: at most %(n)s rows per import.") % {"n": MAX_ROWS}))
            break
        row = {(k or "").strip(): (v or "") for k, v in row.items()}
        name = row.get(lower["challenge"], "").strip()
        if not name and not any(v.strip() for v in row.values()):
            continue  # blank line
        challenge = challenges.get(name.lower())
        if challenge is None:
            report.errors.append((line, _("Unknown challenge “%(name)s”.") % {"name": name}))
            continue
        day = parse_date(row.get(lower["date"], "").strip())
        if day is None:
            report.errors.append((line, _("Invalid date (expected YYYY-MM-DD).")))
            continue
        fields = {f.label.lower(): f for f in challenge.fields.all() if f.is_active}
        fields.update({f.key.lower(): f for f in challenge.fields.all() if f.is_active})
        values = {}
        for header in headers:
            if header.lower() in RESERVED:
                continue
            f = fields.get(header.lower())
            value = _normalise_value(row.get(header, ""))
            if f is not None and value != "":
                values[f.key] = value
        note = _normalise_value(row.get(lower["note"], ""))[:2000] if "note" in lower else ""
        if _is_duplicate(challenge, day, values, note):
            report.skipped += 1
            continue
        try:
            with transaction.atomic():
                create_entry(user, challenge, day, values, note, source=ChallengeEntry.Source.MANUAL)
            report.created += 1
        except ValidationError as exc:
            detail = "; ".join(f"{k}: {' '.join(v)}" if k != "__all__" else " ".join(v) for k, v in getattr(exc, "message_dict", {"__all__": exc.messages}).items())
            report.errors.append((line, detail))
    return report


def _is_duplicate(challenge, day, values: dict, note: str) -> bool:
    for entry in ChallengeEntry.objects.filter(challenge=challenge, date=day).prefetch_related("values__field"):
        existing = {k: _canonical(v) for k, v in entry_values_dict(entry).items() if v not in (None, "")}
        incoming = {k: _canonical(v) for k, v in values.items()}
        if existing == incoming and (entry.note or "") == (note or ""):
            return True
    return False


def _canonical(value) -> str:
    text = str(value).strip().lower()
    if text in {"true", "yes", "1", "done", "oui"}:
        return "true"
    if text in {"false", "no", "0", "non"}:
        return "false"
    if TIME_RE.match(text):
        return text[:5]
    try:
        number = float(text.replace(",", "."))
        return f"{number:g}"
    except ValueError:
        return text
