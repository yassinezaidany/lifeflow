from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.dashboard.views import landing

admin.site.site_header = "LifeFlow administration"
admin.site.site_title = "LifeFlow admin"

urlpatterns = [
    path("", landing, name="landing"),
    path("", include("apps.dashboard.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("challenges/", include("apps.challenges.urls")),
    path("planner/", include("apps.planner.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("reports/", include("apps.reports.urls")),
    path("journal/", include("apps.journal.urls")),
    path("api/", include("config.api_urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
