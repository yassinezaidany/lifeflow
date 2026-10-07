"""Public-deployment features: Alpine scope of every page, cron endpoint, database media storage,
Brevo e-mail backend, privacy page."""
import json
from html.parser import HTMLParser
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from apps.core.models import StoredFile
from apps.core.storage import DatabaseStorage

from .test_pages import PAGES

pytestmark = pytest.mark.django_db

# ---------------------------------------------------------------------------------- Alpine scope
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
ALPINE_ATTR_PREFIXES = ("@", "x-on:", ":", "x-bind:")
ALPINE_ATTRS = {"x-show", "x-text", "x-html", "x-model", "x-if", "x-for", "x-effect", "x-ref", "x-transition", "x-trap"}


class AlpineScopeChecker(HTMLParser):
    """Finds elements carrying Alpine directives that are not inside any x-data component.

    Alpine silently ignores such directives — that is how the "Record" buttons once did nothing."""

    def __init__(self):
        super().__init__()
        self.stack: list[tuple[str, bool]] = []  # (tag, inside x-data)
        self.orphans: list[str] = []

    def handle_starttag(self, tag, attrs):
        names = [name for name, _value in attrs]
        scoped = (self.stack[-1][1] if self.stack else False) or "x-data" in names
        directive = [n for n in names if n.startswith(ALPINE_ATTR_PREFIXES) or n.split(".")[0] in ALPINE_ATTRS]
        if directive and not scoped:
            self.orphans.append(f"<{tag} {' '.join(directive)}> {dict(attrs).get('class', '')[:40]}")
        if tag not in VOID:
            self.stack.append((tag, scoped))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):  # tolerate unclosed elements
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return


def orphans_in(html: str) -> list[str]:
    checker = AlpineScopeChecker()
    checker.feed(html)
    return checker.orphans


def test_checker_detects_the_record_button_bug():
    assert orphans_in('<main><button @click="$dispatch(\'lf:entry\')">Record</button></main>')
    assert not orphans_in('<main x-data><button @click="go()">Record</button></main>')


@pytest.fixture
def demo_client(client):
    call_command("seed_demo", verbosity=0)
    client.force_login(get_user_model().objects.get(username="demo"))
    return client


def test_every_interactive_element_is_inside_an_alpine_component(demo_client):
    from apps.challenges.models import Challenge

    urls = [reverse(name) for name in PAGES] + ["/analytics/achievements/", "/community/", "/reports/import/", "/notifications/"]
    urls += [reverse("challenges:detail", args=[c.pk]) for c in Challenge.objects.filter(user__username="demo")[:2]]
    problems = {}
    for url in urls:
        response = demo_client.get(url)
        assert response.status_code == 200, url
        found = orphans_in(response.content.decode())
        if found:
            problems[url] = found[:5]
    assert not problems, json.dumps(problems, indent=1)


# ---------------------------------------------------------------------------------- cron endpoint
URL = "/internal/cron/reminders/"


def test_cron_disabled_without_token(client):
    assert client.get(URL).status_code == 404


@override_settings(CRON_TOKEN="s3cret-token")
def test_cron_requires_the_token_and_runs_reminders(client):
    from django.core.cache import cache

    cache.delete("cron-reminders-lock")
    assert client.get(URL).status_code == 404
    assert client.get(URL, HTTP_X_CRON_TOKEN="wrong").status_code == 404
    with mock.patch("apps.notifications.reminders.run_all", return_value=3) as run:
        response = client.post(URL, HTTP_X_CRON_TOKEN="s3cret-token")   # no CSRF token needed
        assert response.status_code == 200 and response.json() == {"status": "ok", "sent": 3}
        assert client.get(URL + "?token=s3cret-token").json() == {"status": "skipped"}   # once per minute
        assert run.call_count == 1


# ---------------------------------------------------------------------------------- database storage
def test_database_storage_roundtrip():
    storage = DatabaseStorage()
    name = storage.save("avatars/user_1.png", ContentFile(b"\x89PNG-data", name="user_1.png"))
    assert storage.exists(name) and storage.size(name) == 9
    assert storage.open(name).read() == b"\x89PNG-data"
    second = storage.save("avatars/user_1.png", ContentFile(b"other"))
    assert second != name                                   # never overwrites silently
    assert storage.listdir("avatars") == ([], sorted([name.split("/")[-1], second.split("/")[-1]]))
    assert storage.url(name) == "/media/" + name
    storage.delete(name)
    assert not storage.exists(name) and StoredFile.objects.count() == 1


@override_settings(STORAGES={"default": {"BACKEND": "apps.core.storage.DatabaseStorage"},
                             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
def test_media_view_serves_database_files(client):
    from django.core.files.storage import default_storage

    name = default_storage.save("avatars/a.png", ContentFile(b"img"))
    response = client.get("/media/" + name)
    assert response.status_code == 200 and b"".join(response.streaming_content) == b"img"
    assert response["Content-Type"] == "image/png" and response["X-Content-Type-Options"] == "nosniff"
    assert client.get("/media/avatars/missing.png").status_code == 404
    assert client.get("/media/../config/settings/base.py").status_code == 404


# ---------------------------------------------------------------------------------- Brevo backend
class FakeResponse:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@override_settings(EMAIL_BACKEND="apps.core.mail.BrevoEmailBackend", BREVO_API_KEY="key-123")
def test_brevo_backend_posts_to_the_api():
    with mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
        msg = mail.EmailMultiAlternatives("Hello", "Plain body", "LifeFlow <bot@example.com>", ["Ana <ana@example.com>"])
        msg.attach_alternative("<p>Html body</p>", "text/html")
        assert msg.send() == 1
    request = urlopen.call_args[0][0]
    payload = json.loads(request.data)
    assert request.full_url == "https://api.brevo.com/v3/smtp/email" and request.get_header("Api-key") == "key-123"
    assert payload["sender"] == {"email": "bot@example.com", "name": "LifeFlow"}
    assert payload["to"] == [{"email": "ana@example.com", "name": "Ana"}]
    assert payload["htmlContent"] == "<p>Html body</p>" and payload["textContent"] == "Plain body"


@override_settings(EMAIL_BACKEND="apps.core.mail.BrevoEmailBackend", BREVO_API_KEY="")
def test_brevo_without_key_never_breaks_password_reset(client):
    get_user_model().objects.create_user("zoe", "zoe@example.com", "Str0ng-pass!")
    response = client.post(reverse("accounts:password_reset"), {"email": "zoe@example.com"})
    assert response.status_code == 302


# ---------------------------------------------------------------------------------- privacy page
def test_privacy_page_is_public(client):
    response = client.get(reverse("accounts:privacy"))
    assert response.status_code == 200 and b"accounts/login" in response.content
    assert reverse("accounts:privacy").encode() in client.get(reverse("accounts:login")).content


@override_settings(STORAGES={"default": {"BACKEND": "apps.core.storage.DatabaseStorage"},
                             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
def test_avatar_survives_without_disk(web, user):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    user.profile.avatar.save("me.png", ContentFile(buf.getvalue()), save=True)
    assert StoredFile.objects.filter(name=user.profile.avatar.name).exists()
    response = web.get(user.profile.avatar.url)
    assert response.status_code == 200 and b"".join(response.streaming_content) == buf.getvalue()
