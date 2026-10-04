from datetime import date, timedelta

from django.conf import settings
from django.templatetags.static import static
from django.utils import formats
from django.utils.translation import get_language, get_language_bidi

from .dates import user_today
from .js_i18n import js_translations


def app_context(request):
    ctx = {"APP_NAME": settings.APP_NAME, "theme": "system"}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        profile = getattr(user, "profile", None)
        today = user_today(user)
        ctx["today"] = today
        ctx["unread_notifications"] = user.notifications.filter(is_read=False).count()
        if profile is not None:
            ctx["theme"] = profile.theme
            ctx["profile"] = profile
        monday = date(2024, 1, 1)  # a Monday
        ctx["lf_config"] = {
            "today": today.isoformat(),
            "locale": "ar-u-nu-latn" if (get_language() or "").startswith("ar") else (get_language() or "en"),
            "rtl": get_language_bidi(),
            "timeFormat": profile.time_format if profile else "24h",
            "weekStart": profile.week_start if profile else 0,
            "sprite": static("icons/sprite.svg"),
            "unread": ctx["unread_notifications"],
            "weekdays": [formats.date_format(monday + timedelta(days=i), "D") for i in range(7)],
            "i18n": js_translations(),
        }
    return ctx
