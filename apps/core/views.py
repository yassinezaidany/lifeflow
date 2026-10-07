"""Infrastructure endpoints: uploaded media and the HTTP-triggered reminder run."""
from __future__ import annotations

import mimetypes
import secrets

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import SuspiciousOperation
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


def media_file(request, path):
    """Serve an uploaded file from the configured storage (disk or database)."""
    if ".." in path.split("/") or not path:
        raise Http404
    try:
        f = default_storage.open(path)
    except (FileNotFoundError, OSError, ValueError, SuspiciousOperation):
        raise Http404
    response = FileResponse(f, content_type=mimetypes.guess_type(path)[0] or "application/octet-stream")
    response["Cache-Control"] = "public, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@csrf_exempt
@never_cache
@require_http_methods(["GET", "POST"])
def cron_reminders(request):
    """Run due reminders when called by an external scheduler (e.g. cron-job.org).

    For hosts without background workers. Protected by CRON_TOKEN (header
    `X-Cron-Token` or `?token=`); disabled (404) when no token is configured.
    """
    expected = getattr(settings, "CRON_TOKEN", "")
    given = request.headers.get("X-Cron-Token") or request.GET.get("token") or ""
    if not expected or not secrets.compare_digest(given.encode(), expected.encode()):
        raise Http404
    if not cache.add("cron-reminders-lock", 1, timeout=50):  # at most one run per minute
        return JsonResponse({"status": "skipped"})
    from apps.notifications.reminders import run_all

    return JsonResponse({"status": "ok", "sent": run_all()})
