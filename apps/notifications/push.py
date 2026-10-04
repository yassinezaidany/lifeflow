"""Web Push delivery (VAPID). Fails soft: a push problem never breaks a user action."""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.utils import timezone

from .models import PushSubscription

logger = logging.getLogger("lifeflow")


def push_enabled() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def send_push(user, title: str, body: str = "", url: str = "", tag: str = "") -> int:
    """Send to every device of `user`. Returns the number of successful deliveries.
    Expired subscriptions (404/410) are removed."""
    if not push_enabled():
        return 0
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:  # pragma: no cover - optional dependency
        return 0
    payload = json.dumps({"title": title, "body": body, "url": url or "/today/", "tag": tag})
    sent = 0
    for sub in PushSubscription.objects.filter(user=user):
        try:
            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                ttl=60 * 60 * 12,
                timeout=5,
            )
            sub.last_success_at = timezone.now()
            sub.save(update_fields=["last_success_at"])
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                sub.delete()
            else:
                logger.warning("Web push failed (%s) for user %s", status, user.pk)
        except Exception:  # network errors, malformed keys…
            logger.exception("Web push error for user %s", user.pk)
    return sent
