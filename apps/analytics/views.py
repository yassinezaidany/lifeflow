from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .services.overview import PERIODS, build_overview


@login_required
def overview(request):
    key = request.GET.get("period", "30d")
    if key not in PERIODS:
        key = "30d"
    ctx = build_overview(request.user, key)
    ctx["chart"] = {
        "challenges": [{"name": r["challenge"].name, "color": r["challenge"].color, "rate": r["progress"].completion_rate or 0,
                        "progress": min(r["progress"].progress or 0, 100)} for r in ctx["rows"]],
        "planner_weeks": ctx["planner_weeks"],
        "categories": ctx["categories"],
        "weekdays": ctx["weekday_counts"],
    }
    return render(request, "analytics/overview.html", ctx)
