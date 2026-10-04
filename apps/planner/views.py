from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts.models import Profile

from apps.core.dates import parse_date, user_today
from apps.core.icons import picker_icons


@login_required
def week(request):
    profile = request.user.profile
    today = user_today(request.user)
    view = request.GET.get("view", "week")
    return render(request, "planner/planner.html", {
        "planner_opts": {
            "mode": view if view in ("week", "day") else "week",
            "date": (parse_date(request.GET.get("date")) or today).isoformat(),
            "today": today.isoformat(),
            "dayStart": profile.planner_day_start,
            "dayEnd": profile.planner_day_end,
        },
    })


FEED_PAST_DAYS, FEED_FUTURE_DAYS = 30, 90


def _ics_response(user, filename, inline=False):
    from .ical import build_ics

    today = user_today(user)
    body = build_ics(user, today - timedelta(days=FEED_PAST_DAYS), today + timedelta(days=FEED_FUTURE_DAYS))
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{filename}"'
    response["Cache-Control"] = "private, max-age=300"
    return response


@login_required
def export_ics(request):
    return _ics_response(request.user, "lifeflow-planner.ics")


def calendar_feed(request, token):
    """Read-only subscription feed for calendar apps (authenticated by a secret token)."""
    profile = Profile.objects.filter(calendar_token=token).select_related("user").first()
    if profile is None or not profile.user.is_active:
        raise Http404
    return _ics_response(profile.user, "lifeflow.ics", inline=True)


@login_required
@require_POST
def regenerate_feed(request):
    request.user.profile.ensure_calendar_token(regenerate=True)
    messages.success(request, _("A new calendar link was created. The previous link no longer works."))
    return redirect(request.POST.get("next") or "accounts:settings")


@login_required
def rules(request):
    return render(request, "planner/rules.html", {"today": user_today(request.user)})


@login_required
def templates(request):
    return render(request, "planner/templates.html", {"icons": picker_icons()})
