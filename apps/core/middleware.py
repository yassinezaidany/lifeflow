from django.utils import timezone, translation

from .dates import user_tz


class UserPreferencesMiddleware:
    """Activate the authenticated user's timezone and language for the request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            timezone.activate(user_tz(user))
            profile = getattr(user, "profile", None)
            if profile is not None and profile.language:
                translation.activate(profile.language)
                request.LANGUAGE_CODE = profile.language
        else:
            timezone.deactivate()
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Conservative Content-Security-Policy: only first-party assets may load.

    Alpine.js evaluates expressions with `new Function`, hence 'unsafe-eval'.
    """

    CSP = "; ".join(
        [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
