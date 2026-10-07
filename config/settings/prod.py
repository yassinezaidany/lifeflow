"""Production settings.

By default LifeFlow expects HTTPS (reverse proxy / TLS terminator in front of Django):
secure cookies, HSTS and HTTP→HTTPS redirect are on. For a personal install on a
local machine or a home network without TLS, set `USE_HTTPS=False` in `.env`
(service worker and Web Push then only work on http://localhost).
"""
from .base import *  # noqa: F401,F403

DEBUG = False

USE_HTTPS = env.bool("USE_HTTPS", default=True)  # noqa: F405

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=USE_HTTPS)  # noqa: F405
SESSION_COOKIE_SECURE = USE_HTTPS
CSRF_COOKIE_SECURE = USE_HTTPS
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30 if USE_HTTPS else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = USE_HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]  # container health checks run over plain HTTP

STORAGES = {
    "default": {"BACKEND": DEFAULT_FILE_STORAGE_BACKEND},  # noqa: F405
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
