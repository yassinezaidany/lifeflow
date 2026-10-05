from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from apps.core import pwa
from apps.dashboard.views import landing

admin.site.site_header = "LifeFlow administration"
admin.site.site_title = "LifeFlow admin"

urlpatterns = [
    path("", landing, name="landing"),
    path("sw.js", pwa.service_worker, name="service-worker"),
    path("manifest.webmanifest", pwa.manifest, name="manifest"),
    path("offline/", pwa.offline, name="offline"),
    path("healthz", pwa.health, name="health"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("apps.dashboard.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("challenges/", include("apps.challenges.urls")),
    path("planner/", include("apps.planner.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("reports/", include("apps.reports.urls")),
    path("journal/", include("apps.journal.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("api/", include("config.api_urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, "SERVE_MEDIA", False):
    # Simple single-server deployment: Django serves the (small) uploaded avatars itself.
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
