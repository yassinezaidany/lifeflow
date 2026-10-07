"""E-mail backend using Brevo's HTTPS API (free plan: 300 e-mails/day).

For hosts that block outbound SMTP ports. Enable with
EMAIL_BACKEND=apps.core.mail.BrevoEmailBackend and BREVO_API_KEY=… ; the sender address
(DEFAULT_FROM_EMAIL) must be a sender verified in the Brevo account.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger("lifeflow")
API_URL = "https://api.brevo.com/v3/smtp/email"


def _contact(address: str) -> dict:
    name, email = parseaddr(address)
    return {"email": email, **({"name": name} if name else {})}


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages) -> int:
        api_key = getattr(settings, "BREVO_API_KEY", "")
        if not api_key:  # e-mail not configured yet: never break the page that tried to send
            logger.warning("E-mail not sent: BREVO_API_KEY is not configured")
            return 0
        sent = 0
        for message in email_messages:
            payload = {
                "sender": _contact(message.from_email or settings.DEFAULT_FROM_EMAIL),
                "to": [_contact(a) for a in message.to],
                "subject": message.subject,
                "textContent": message.body or " ",
            }
            if message.cc:
                payload["cc"] = [_contact(a) for a in message.cc]
            if message.bcc:
                payload["bcc"] = [_contact(a) for a in message.bcc]
            if message.reply_to:
                payload["replyTo"] = _contact(message.reply_to[0])
            for content, mimetype in getattr(message, "alternatives", []):
                if mimetype == "text/html":
                    payload["htmlContent"] = content
            request = urllib.request.Request(
                API_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
                headers={"api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    if 200 <= response.status < 300:
                        sent += 1
            except (urllib.error.URLError, TimeoutError) as exc:
                logger.warning("Brevo e-mail failed: %s", exc)
                if not self.fail_silently:
                    raise
        return sent
