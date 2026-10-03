"""Monthly report generation: computes everything once and freezes it in a snapshot."""
from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.analytics.services.progress import ProgressEngine
from apps.challenges.models import Challenge
from apps.core.audit import audit
from apps.core.dates import month_bounds, user_today
from apps.core.models import AuditLog
from apps.notifications.services import notify
from apps.notifications.models import Notification
from apps.planner import services as planner
from apps.planner.models import PlannedActivity

from ..models import MonthlyReport, ReportChallengeSnapshot


@transaction.atomic
def generate_monthly_report(user, year: int, month: int) -> MonthlyReport:
    if not 1 <= month <= 12:
        raise ValidationError({"month": _("Invalid month.")})
    start, end = month_bounds(year, month)
    today = user_today(user)
    if start > today:
        raise ValidationError({"month": _("You can't generate a report for a future month.")})

    closed = end < today
    as_of = end if closed else today
    challenges = list(ProgressEngine.prefetch(
        Challenge.objects.filter(user=user, start_date__lte=end).exclude(end_date__lt=start).select_related("category")
    ))
    engine = ProgressEngine(user, as_of=as_of, day_closed=closed)
    results = engine.evaluate_many(challenges, include_series=True, window=(start, end))

    version = (MonthlyReport.objects.filter(user=user, year=year, month=month).aggregate(v=Max("version"))["v"] or 0) + 1
    planner.ensure_occurrences(user, start, min(end, today))
    acts = list(PlannedActivity.objects.filter(user=user, date__range=(start, end)))
    planner_summary = planner.summarize(acts, user)

    snapshots = []
    for order, c in enumerate(challenges):
        r = results[c.pk]
        snapshots.append(ReportChallengeSnapshot(
            challenge=c, name=c.name, category=c.category.name if c.category else "", color=c.color,
            goal_description=r.goal_description[:160], unit=r.unit[:30], is_duration=r.is_duration,
            goal=r.goal, actual=r.actual, expected=r.expected, progress=r.progress, gap=r.gap,
            status=r.status.value, completion_rate=r.completion_rate, current_streak=r.current_streak,
            best_streak=r.best_streak, streak_unit=r.streak_unit, average=r.average,
            active_days=r.statistics.get("active_days", 0), completed_periods=r.completed_periods,
            due_periods=r.due_periods, daily_series=[[d.date.isoformat(), round(d.actual, 2), d.status] for d in r.days],
            order=order,
        ))

    rates = [s.completion_rate for s in snapshots if s.completion_rate is not None]
    summary = {
        "challenges": len(snapshots),
        "active": sum(1 for c in challenges if c.status == Challenge.Status.ACTIVE),
        "completed": sum(1 for s in snapshots if s.status == "completed"),
        "average_completion": round(sum(rates) / len(rates), 1) if rates else None,
        "average_progress": round(sum(min(s.progress or 0, 100) for s in snapshots) / len(snapshots), 1) if snapshots else None,
        "entries": sum(results[c.pk].statistics.get("entries", 0) for c in challenges),
        "best_streak": max((s.best_streak for s in snapshots), default=0),
        "is_partial": not closed,
        "as_of": as_of.isoformat(),
    }
    report = MonthlyReport.objects.create(
        user=user, year=year, month=month, version=version, period_start=start, period_end=end,
        generated_at=timezone.now(), user_display_name=user.get_full_name() or user.username,
        timezone=user.profile.timezone, summary=summary, planner=planner_summary,
    )
    for s in snapshots:
        s.report = report
    ReportChallengeSnapshot.objects.bulk_create(snapshots)
    audit(user, AuditLog.Action.REPORT_GENERATED, report, year=year, month=month, version=version)
    notify(user, Notification.Kind.REPORT_READY, _("Your report for %(period)s is ready") % {"period": date(year, month, 1).strftime("%B %Y")},
           url=f"/reports/{report.pk}/", setting="notify_report_ready")
    return report
