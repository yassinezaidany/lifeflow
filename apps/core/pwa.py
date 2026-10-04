"""Progressive Web App endpoints: service worker (root scope), manifest and offline page."""
import hashlib
from functools import lru_cache

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

# Files precached by the service worker (the "app shell").
SHELL_STATIC = [
    "css/app.css", "js/app.js", "js/planner.js", "js/challenges.js",
    "vendor/alpine.min.js", "vendor/alpine-focus.min.js", "vendor/alpine-collapse.min.js", "vendor/chart.umd.min.js",
    "icons/sprite.svg", "fonts/inter-latin-wght-normal.woff2", "img/logo.svg", "img/favicon.svg",
    "img/icons/icon-192.png",
]


@lru_cache(maxsize=1)
def shell_version() -> str:
    """Content hash of the app shell: a new deploy automatically invalidates old caches."""
    digest = hashlib.sha256()
    for rel in SHELL_STATIC:
        path = settings.BASE_DIR / "static" / rel
        if path.exists():
            digest.update(path.read_bytes())
    digest.update(b"sw-v3")
    return digest.hexdigest()[:12]


@require_GET
@cache_control(no_cache=True, max_age=0)
def service_worker(request):
    response = render(request, "pwa/sw.js", {
        "version": shell_version(),
        "shell": [static(p) for p in SHELL_STATIC],
        "offline_url": "/offline/",
        "icon": static("img/icons/icon-192.png"),
    }, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response


@require_GET
@cache_control(max_age=60 * 60)
def manifest(request):
    return JsonResponse({
        "name": "LifeFlow",
        "short_name": "LifeFlow",
        "description": "Personal challenges, planner & progress",
        "id": "/",
        "start_url": "/today/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#F7F7F8",
        "theme_color": "#4F46E5",
        "lang": getattr(request, "LANGUAGE_CODE", "en"),
        "icons": [
            {"src": static("img/icons/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("img/icons/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": static("img/icons/maskable-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": static("img/icons/maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "Today", "url": "/today/", "icons": [{"src": static("img/icons/icon-192.png"), "sizes": "192x192"}]},
            {"name": "Planner", "url": "/planner/", "icons": [{"src": static("img/icons/icon-192.png"), "sizes": "192x192"}]},
        ],
    }, content_type="application/manifest+json")


@require_GET
def offline(request):
    return render(request, "pwa/offline.html")


def health(request):
    return HttpResponse("ok", content_type="text/plain")
