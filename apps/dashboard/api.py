from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.dates import parse_date, user_today

from . import services


def _card(card):
    c, p = card["challenge"], card["progress"]
    return {"id": c.pk, "name": c.name, "color": c.color, "icon": c.icon, "status": c.status, "progress": p.as_dict(include_series=False)}


@api_view(["GET"])
def dashboard(request):
    data = services.build_dashboard(request.user)
    return Response({
        "greeting": data["greeting"],
        "today": data["today"].isoformat(),
        "planner": data["summary"],
        "upcoming": [{"id": a.pk, "title": a.title, "start_time": a.start_time.strftime("%H:%M"),
                      "end_time": a.end_time.strftime("%H:%M"), "color": a.effective_color} for a in data["upcoming"]],
        "challenges": [_card(c) for c in data["cards"]],
        "overall_progress": data["overall_progress"],
        "done_today": data["done_today"],
        "today_challenges": len(data["today_challenges"]),
        "streaks": [{"id": c["challenge"].pk, "name": c["challenge"].name, "streak": c["progress"].current_streak,
                     "unit": c["progress"].streak_unit} for c in data["streaks"]],
        "last7": [{**d, "date": d["date"].isoformat()} for d in data["last7"]],
    })


@api_view(["GET"])
def calendar(request):
    today = user_today(request.user)
    try:
        year, month = (int(x) for x in (request.query_params.get("month") or f"{today:%Y-%m}").split("-"))
        assert 1 <= month <= 12 and 2000 <= year <= 2100
    except (ValueError, AssertionError):
        year, month = today.year, today.month
    data = services.build_calendar(request.user, year, month)
    return Response({
        "year": year, "month": month,
        "weeks": [[{
            "date": d["date"].isoformat(), "in_month": d["in_month"], "is_today": d["is_today"],
            "planner": d["summary"], "challenges": d["challenges"], "done": d["done"], "missed": d["missed"],
            "rest": d["rest"], "journal": d["journal"],
        } for d in week] for week in data["weeks"]],
    })


@api_view(["GET"])
def calendar_day(request):
    day = parse_date(request.query_params.get("date"), user_today(request.user))
    data = services.build_day_detail(request.user, day)
    return Response({
        "date": day.isoformat(),
        "planner": data["summary"],
        "activities": [{"id": a.pk, "title": a.title, "status": a.status, "start_time": a.start_time.strftime("%H:%M"),
                        "end_time": a.end_time.strftime("%H:%M")} for a in data["activities"]],
        "challenges": [{"id": r["challenge"].pk, "name": r["challenge"].name, **r["point"].as_dict()} for r in data["challenges"]],
        "entries": [{"id": e.pk, "challenge": e.challenge.name, "values": {v.field.label: v.value for v in e.values.all()}, "note": e.note}
                    for e in data["entries"]],
        "journal": [{"id": j.pk, "title": j.title, "content": j.content} for j in data["journal"]],
        "rest": data["rest"],
    })
