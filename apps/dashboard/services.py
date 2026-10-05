"""Read-model aggregation for the dashboard, Today view, calendar and weekly review.
All progress numbers come from the ProgressEngine (no logic duplicated here)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.utils.translation import gettext as _

from apps.analytics.services.insights import build_insights
from apps.analytics.services.progress import ProgressEngine, ProgressStatus
from apps.challenges.models import Challenge, RestDay
from apps.core.dates import month_bounds, user_now, user_today, week_start_for
from apps.journal.models import JournalEntry, WeeklyReview
from apps.planner import services as planner
from apps.planner.models import PlannedActivity
from apps.tracking.models import ChallengeEntry

ACTIVE_STATUSES = [Challenge.Status.ACTIVE, Challenge.Status.PAUSED]


def greeting(user) -> str:
    hour = user_now(user).hour
    if hour < 5:
        return _("Good night")
    if hour < 12:
        return _("Good morning")
    if hour < 18:
        return _("Good afternoon")
    return _("Good evening")


def active_challenges(user, statuses=None):
    qs = Challenge.objects.filter(user=user, status__in=statuses or ACTIVE_STATUSES)
    return list(ProgressEngine.prefetch(qs).prefetch_related("fields"))


def challenge_cards(user, challenges=None, as_of=None):
    challenges = active_challenges(user) if challenges is None else challenges
    results = ProgressEngine(user, as_of=as_of).evaluate_many(challenges)
    return [{"challenge": c, "progress": results[c.pk]} for c in challenges]


def today_activities(user, day: date | None = None):
    day = day or user_today(user)
    planner.ensure_occurrences(user, day, day)
    return list(PlannedActivity.objects.filter(user=user, date=day).select_related("category", "challenge"))


def build_dashboard(user) -> dict:
    today = user_today(user)
    now = user_now(user)
    activities = today_activities(user, today)
    cards = challenge_cards(user)
    visible = [a for a in activities if a.status not in (PlannedActivity.Status.CANCELLED, PlannedActivity.Status.RESCHEDULED)]
    upcoming = [
        a for a in visible
        if a.status in (PlannedActivity.Status.PLANNED, PlannedActivity.Status.IN_PROGRESS)
        and not planner.is_overdue(a, now)
    ][:5]

    running = [c for c in cards if c["challenge"].status == Challenge.Status.ACTIVE and c["progress"].status != ProgressStatus.NOT_STARTED]
    today_challenges = [c for c in running if c["progress"].today.get("type") == "active" or c["progress"].today.get("done")]
    progress_values = [c["progress"].progress_capped for c in running if c["progress"].progress is not None]
    streaks = sorted((c for c in running if c["progress"].current_streak > 0), key=lambda c: -c["progress"].current_streak)[:4]

    # Last 7 days: planner completion + challenge entries (one query each)
    week_start = today - timedelta(days=6)
    planner.ensure_occurrences(user, week_start, today)
    week_acts = list(PlannedActivity.objects.filter(user=user, date__range=(week_start, today)))
    entries_by_day = defaultdict(int)
    for d in ChallengeEntry.objects.filter(user=user, date__range=(week_start, today)).values_list("date", flat=True):
        entries_by_day[d] += 1
    last7 = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        summary = planner.summarize([a for a in week_acts if a.date == d], user)
        last7.append({"date": d, "planner_rate": summary["completion_rate"], "planned": summary["planned"],
                      "completed": summary["completed"], "entries": entries_by_day.get(d, 0)})

    return {
        "greeting": greeting(user),
        "today": today,
        "summary": planner.summarize(activities, user),
        "upcoming": upcoming,
        "cards": cards,
        "running": running,
        "today_challenges": today_challenges,
        "done_today": sum(1 for c in today_challenges if c["progress"].today.get("done")),
        "overall_progress": round(sum(progress_values) / len(progress_values), 1) if progress_values else None,
        "streaks": streaks,
        "last7": last7,
        "status_counts": _status_counts(running),
        "insights": build_insights(user, running, limit=3),
    }


def _status_counts(cards) -> dict:
    counts = defaultdict(int)
    for c in cards:
        counts[c["progress"].status.value] += 1
    return dict(counts)


def build_calendar(user, year: int, month: int) -> dict:
    start, end = month_bounds(year, month)
    profile = user.profile
    grid_start = week_start_for(start, profile.week_start)
    grid_end = week_start_for(end, profile.week_start) + timedelta(days=6)
    today = user_today(user)

    planner.ensure_occurrences(user, grid_start, grid_end)
    acts = list(PlannedActivity.objects.filter(user=user, date__range=(grid_start, grid_end)).select_related("category"))
    challenges = list(ProgressEngine.prefetch(
        Challenge.objects.filter(user=user, start_date__lte=grid_end).exclude(status=Challenge.Status.ARCHIVED)
    ))
    results = ProgressEngine(user).evaluate_many(challenges, include_series=True, window=(grid_start, grid_end))
    challenge_days: dict[date, list] = defaultdict(list)
    for c in challenges:
        for point in results[c.pk].days:
            if point.status not in ("outside",):
                challenge_days[point.date].append({"id": c.pk, "name": c.name, "color": c.color, "status": point.status})
    rest = set(RestDay.objects.filter(user=user, challenge__isnull=True, date__range=(grid_start, grid_end)).values_list("date", flat=True))
    journal = set(JournalEntry.objects.filter(user=user, date__range=(grid_start, grid_end)).values_list("date", flat=True))

    weeks, day = [], grid_start
    while day <= grid_end:
        week = []
        for _i in range(7):
            day_acts = [a for a in acts if a.date == day]
            summary = planner.summarize(day_acts, user)
            chs = challenge_days.get(day, [])
            week.append({
                "date": day,
                "in_month": day.month == month,
                "is_today": day == today,
                "is_future": day > today,
                "summary": summary,
                "activities": [a for a in day_acts if a.status not in (PlannedActivity.Status.CANCELLED, PlannedActivity.Status.RESCHEDULED)][:3],
                "challenges": chs,
                "done": sum(1 for c in chs if c["status"] == "done"),
                "missed": sum(1 for c in chs if c["status"] == "missed"),
                "rest": day in rest,
                "journal": day in journal,
            })
            day += timedelta(days=1)
        weeks.append(week)
    prev_month = (start - timedelta(days=1)).replace(day=1)
    next_month = end + timedelta(days=1)
    return {"year": year, "month": month, "start": start, "weeks": weeks, "prev": prev_month, "next": next_month}


def build_day_detail(user, day: date) -> dict:
    activities = today_activities(user, day)
    challenges = list(ProgressEngine.prefetch(
        Challenge.objects.filter(user=user, start_date__lte=day).exclude(status=Challenge.Status.ARCHIVED)
    ))
    results = ProgressEngine(user).evaluate_many(challenges, include_series=True, window=(day, day))
    rows = []
    for c in challenges:
        points = results[c.pk].days
        if points and points[0].status != "outside":
            r = results[c.pk]
            g = r.goal_obj
            measurable = g is not None and g.aggregation == g.Aggregation.SUM and g.metric is not None and g.metric.field_type != "boolean"
            rows.append({"challenge": c, "point": points[0], "progress": r,
                         "display": f"{r.fmt(points[0].actual)} {r.unit}".strip() if measurable else ""})
    entries = list(ChallengeEntry.objects.filter(user=user, date=day).select_related("challenge").prefetch_related("values__field"))
    return {
        "date": day,
        "activities": activities,
        "summary": planner.summarize(activities, user),
        "challenges": rows,
        "entries": entries,
        "journal": list(JournalEntry.objects.filter(user=user, date=day)),
        "rest": RestDay.objects.filter(user=user, challenge__isnull=True, date=day).exists(),
    }


def build_weekly_review(user, anchor: date | None = None) -> dict:
    profile = user.profile
    anchor = anchor or user_today(user)
    start = week_start_for(anchor, profile.week_start)
    end = start + timedelta(days=6)
    today = user_today(user)
    challenges = list(ProgressEngine.prefetch(
        Challenge.objects.filter(user=user, start_date__lte=end).exclude(status=Challenge.Status.ARCHIVED)
    ))
    closed = end < today
    engine = ProgressEngine(user, as_of=end if closed else today, day_closed=closed)
    results = engine.evaluate_many(challenges, include_series=True, window=(start, end))
    rows = [{"challenge": c, "progress": results[c.pk]} for c in challenges if results[c.pk].goal > 0 or results[c.pk].actual > 0]
    achieved = sum(1 for r in rows if r["progress"].goal > 0 and r["progress"].actual >= r["progress"].goal - 1e-9)
    planner.ensure_occurrences(user, start, end)
    acts = list(PlannedActivity.objects.filter(user=user, date__range=(start, end)))
    review = WeeklyReview.objects.filter(user=user, week_start=start).first()
    return {
        "start": start, "end": end, "rows": rows, "achieved": achieved, "total": len(rows),
        "best_streak": max((r["progress"].current_streak for r in rows), default=0),
        "planner": planner.summarize(acts, user), "review": review,
        "prev": start - timedelta(days=7), "next": start + timedelta(days=7) if start + timedelta(days=7) <= today else None,
        "is_current": start <= today <= end,
    }
