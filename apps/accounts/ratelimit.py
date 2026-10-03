"""Small cache-based limiter for login attempts (brute-force protection)."""
from django.conf import settings
from django.core.cache import cache


def _client_ip(request) -> str:
    return request.META.get("REMOTE_ADDR", "unknown")


def _key(request, identifier: str) -> str:
    return f"login-attempts:{_client_ip(request)}:{(identifier or '').lower()[:150]}"


def is_rate_limited(request, identifier: str) -> bool:
    return cache.get(_key(request, identifier), 0) >= settings.LOGIN_RATE_LIMIT_ATTEMPTS


def register_failure(request, identifier: str) -> None:
    key = _key(request, identifier)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, settings.LOGIN_RATE_LIMIT_WINDOW)


def reset(request, identifier: str) -> None:
    cache.delete(_key(request, identifier))
