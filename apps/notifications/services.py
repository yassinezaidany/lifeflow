"""In-app notifications. Optional by design: every sender checks the user's preferences,
and the app is fully usable with notifications disabled."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction

from .models import Notification

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
    if prefs is not None and prefs.email_notifications and user.email:
        try:
            send_mail(title, f"{body}\n\n{url}".strip(), settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
        except Exception:  # pragma: no cover
            logger.exception("Notification email failed")
    return notification
