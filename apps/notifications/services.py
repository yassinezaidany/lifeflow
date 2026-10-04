"""In-app notifications, optionally mirrored to Web Push and e-mail.

Optional by design: every sender checks the user's preferences, and the app is
fully usable with notifications disabled."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import translation

from .models import Notification
from .push import send_push

logger = logging.getLogger("lifeflow")


def notify(user, kind: str, title: str, body: str = "", url: str = "", dedupe_key: str | None = None, setting: str | None = None):
    prefs = getattr(user, "settings", None)
    if prefs is not None:
        if not prefs.notifications_enabled or (setting and not getattr(prefs, setting, True)):
            return None
    try:
        with transaction.atomic():
            notification = Notification.objects.create(
                user=user, kind=kind, title=title[:140], body=body[:500], url=url[:300], dedupe_key=dedupe_key
            )
    except IntegrityError:
        return None  # already sent (dedupe)

    if prefs is None or prefs.push_notifications:
        send_push(user, notification.title, notification.body, notification.url, tag=kind)
    if prefs is not None and prefs.email_notifications and user.email:
        _send_email(user, notification)
    return notification


def _send_email(user, notification) -> None:
    link = settings.SITE_URL.rstrip("/") + (notification.url or "/today/")
    language = getattr(getattr(user, "profile", None), "language", None) or settings.LANGUAGE_CODE
    with translation.override(language):
        context = {"user": user, "notification": notification, "link": link}
        html = render_to_string("notifications/email.html", context)
        text = f"{notification.body}\n\n{link}".strip()
    try:
        send_mail(notification.title, text, settings.DEFAULT_FROM_EMAIL, [user.email], html_message=html, fail_silently=False)
    except Exception:  # pragma: no cover - SMTP problems must not break the app
        logger.exception("Notification email failed for user %s", user.pk)
