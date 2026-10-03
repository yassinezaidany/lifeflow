import logging

from .models import AuditLog

logger = logging.getLogger("lifeflow")


def audit(user, action: str, obj=None, description: str = "", **metadata) -> AuditLog:
    """Record a business event. Never raises: auditing must not break a user action."""
    try:
        return AuditLog.objects.create(
            user=user,
            action=action,
            object_type=obj.__class__.__name__ if obj is not None else "",
            object_id=str(getattr(obj, "pk", "") or ""),
            description=(description or (str(obj) if obj is not None else ""))[:255],
            metadata={k: _jsonable(v) for k, v in metadata.items()},
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Audit log failure for action %s", action)
        return None


def _jsonable(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)
