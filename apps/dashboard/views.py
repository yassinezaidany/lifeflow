from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render

from apps.core.dates import parse_date, user_now, user_today
from apps.planner import services as planner
from apps.planner.api import serialize_activities

from . import services


def landing(request):
    return redirect("dashboard:home" if request.user.is_authenticated else "accounts:login")


@login_required
def home(request):
    ctx = services.build_dashboard(request.user)
    return render(request, "dashboard/home.html", ctx)


@login_required
def today(request):
    day = user_today(request.user)
    activities = services.today_activities(request.user, day)
    visible = [a for a in activities if a.status not in ("rescheduled",) and not (a.status == "cancelled" and a.recurring_rule_id)]
    serialized = {a["id"]: a for a in serialize_activities(request, visible)}
    now = user_now(request.user)
    cards = services.challenge_cards(request.user)
    running = [c for c in cards if c["challenge"].status == "active" and c["progress"].status.value != "not_started"]
    todo = [c for c in running if c["progress"].today.get("type") == "active" and not c["progress"].today.get("done")]
    done = [c for c in running if c["progress"].today.get("done")]
    rest = [c for c in running if c["progress"].today.get("type") == "rest" and not c["progress"].today.get("done")]
    current = next((a for a in visible if a.status in ("planned", "in_progress") and not planner.is_overdue(a, now)
                    and a.start_time <= now.time()), None)
    return render(request, "dashboard/today.html", {
        "day": day,
        "rows": [{"activity": a, "data": serialized[a.pk], "overdue": serialized[a.pk]["overdue"]} for a in visible],
        "summary": planner.summarize(activities, request.user),
        "todo": todo, "done": done, "rest": rest,
        "current": current,
        "now": now,
    })


@login_required
def calendar(request):
    today_ = user_today(request.user)
    try:
        year, month = (int(x) for x in (request.GET.get("month") or f"{today_:%Y-%m}").split("-"))
        date(year, month, 1)
        if not 2000 <= year <= 2100:
            raise ValueError
    except (ValueError, TypeError):
        year, month = today_.year, today_.month
    ctx = services.build_calendar(request.user, year, month)
    selected = parse_date(request.GET.get("date")) or (today_ if (today_.year, today_.month) == (year, month) else ctx["start"])
    ctx["selected"] = selected
    ctx["detail"] = services.build_day_detail(request.user, selected)
    return render(request, "dashboard/calendar.html", ctx)


@login_required
def day(request, value):
    day_ = parse_date(value)
    if day_ is None:
        raise Http404
    return render(request, "dashboard/day.html", {"detail": services.build_day_detail(request.user, day_)})
