"""Uniform, human-readable API errors. Never leak stack traces or DB errors to clients."""
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("lifeflow")


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        detail = exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
        return Response({"detail": _("Please correct the errors below."), "errors": detail}, status=status.HTTP_400_BAD_REQUEST)

    if isinstance(exc, IntegrityError):
        logger.warning("IntegrityError in API: %s", exc)
        return Response(
            {"detail": _("This change conflicts with existing data (it may already exist).")},
            status=status.HTTP_409_CONFLICT,
        )

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
        return Response({"detail": _("Something went wrong on our side. Please try again.")}, status=500)

    data = response.data
    if isinstance(exc, Http404) or response.status_code == 404:
        response.data = {"detail": _("Not found.")}
    elif isinstance(data, dict) and "detail" not in data:
        response.data = {"detail": _("Please correct the errors below."), "errors": data}
    elif isinstance(data, list):
        response.data = {"detail": " ".join(str(d) for d in data), "errors": {"non_field_errors": data}}
    return response
