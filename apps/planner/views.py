from django.contrib.auth.decorators import login_required
from django.shortcuts import render

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


@login_required
def rules(request):
    return render(request, "planner/rules.html", {"today": user_today(request.user)})


@login_required
def templates(request):
    return render(request, "planner/templates.html", {"icons": picker_icons()})
