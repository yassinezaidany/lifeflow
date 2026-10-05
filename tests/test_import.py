"""CSV import of entries: round-trip with the export, validation, duplicates, isolation."""
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.reports.imports import import_entries_csv
from apps.tracking.models import ChallengeEntry
from apps.tracking.services import create_entry

from .factories import make_challenge

pytestmark = pytest.mark.django_db
START = date(2025, 1, 6)


def reading(user, name="Reading"):
    return make_challenge(user, name=name, start=START, fields=[
        {"label": "Pages", "key": "pages", "field_type": "integer"},
        {"label": "Wake", "key": "wake", "field_type": "time"},
        {"label": "Done", "key": "done", "field_type": "boolean"},
    ], goal={"metric": "pages", "period": "daily", "aggregation": "sum", "target": 5})


def csv_file(text: str, name="entries.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


def test_import_creates_valid_rows_and_reports_errors(user):
    c = reading(user)
    report = import_entries_csv(user, csv_file(
        "Challenge,Date,Pages,Wake,Done,Note\n"
        "reading,2025-01-06,4,06:30,yes,first\n"       # name matched case-insensitively
        "Reading,2025-01-07,-3,,,\n"                    # negative -> error
        "Reading,07/01/2025,3,,,\n"                     # bad date
        "Unknown,2025-01-07,3,,,\n"                     # no such challenge
        "Reading,2025-01-05,3,,,\n"                     # before start
        ",,,,,\n"                                        # blank line ignored
        "Reading,2025-01-08,2,,no,'-tired\n"            # export's formula guard undone
    ))
    assert report.created == 2 and report.skipped == 0
    assert [line for line, _msg in report.errors] == [3, 4, 5, 6]
    entries = list(ChallengeEntry.objects.filter(challenge=c).order_by("date"))
    assert [e.note for e in entries] == ["first", "-tired"]


def test_reimporting_the_export_is_idempotent(user, web):
    c = reading(user)
    create_entry(user, c, START, {"pages": 4, "wake": "06:30", "done": True}, "fine, =ok")
    exported = web.get("/reports/export/?format=csv&kind=entries").content.decode("utf-8-sig")
    report = import_entries_csv(user, csv_file(exported))
    assert (report.created, report.skipped, report.failed) == (0, 1, 0)
    assert ChallengeEntry.objects.filter(challenge=c).count() == 1


def test_semicolon_and_missing_columns(user):
    reading(user)
    report = import_entries_csv(user, csv_file("Challenge;Date;Pages\nReading;2025-01-06;7\n"))
    assert report.created == 1
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        import_entries_csv(user, csv_file("Name,Day\nReading,2025-01-06\n"))


def test_import_never_touches_other_users_challenges(user, other_user):
    reading(other_user)
    report = import_entries_csv(user, csv_file("Challenge,Date,Pages\nReading,2025-01-06,4\n"))
    assert report.created == 0 and report.failed == 1
    assert ChallengeEntry.objects.count() == 0


def test_import_page(web, user):
    reading(user)
    assert web.get("/reports/import/").status_code == 200
    response = web.post("/reports/import/", {"file": csv_file("Challenge,Date,Pages\nReading,2025-01-06,4\n")})
    assert response.status_code == 200 and response.context["report"].created == 1
