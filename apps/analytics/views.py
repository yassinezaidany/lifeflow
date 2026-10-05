from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.dashboard.services import challenge_cards

from .services.achievements import build_achievements
from .services.insights import build_insights
from .services.overview import PERIODS, build_overview


@login_required
def overview(request):
    key = request.GET.get("period", "30d")
    if key not in PERIODS:
        key = "30d"
    ctx = build_overview(request.user, key)
    ctx["insights"] = build_insights(request.user, challenge_cards(request.user), limit=6)
    ctx["chart"] = {
        "challenges": [{"name": r["challenge"].name, "color": r["challenge"].color, "rate": r["progress"].completion_rate or 0,
                        "progress": min(r["progress"].progress or 0, 100)} for r in ctx["rows"]],
        "planner_weeks": ctx["planner_weeks"],
        "categories": ctx["categories"],
        "weekdays": ctx["weekday_counts"],
    }
    return render(request, "analytics/overview.html", ctx)


@login_required
def achievements(request):
    return render(request, "analytics/achievements.html", build_achievements(request.user))
