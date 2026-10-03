from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.analytics.services.progress import ProgressEngine
from apps.core.dates import user_today, week_start_for
from apps.core.icons import picker_icons
from apps.tracking.models import ChallengeEntry

from .models import COLOR_CHOICES, Challenge, ChallengeCategory, ChallengeTemplate
from .serializers import ChallengeCategorySerializer, ChallengeSerializer, ChallengeTemplateSerializer

STATUS_TABS = ["active", "paused", "completed", "archived"]


def _owned(request, pk):
    qs = ProgressEngine.prefetch(Challenge.objects.filter(user=request.user)).prefetch_related("fields")
    return get_object_or_404(qs, pk=pk)


def _categories(user):
    return list(ChallengeCategory.objects.filter(user=user).values("id", "name", "color", "icon"))


@login_required
def challenge_list(request):
    status = request.GET.get("status", "active")
    if status not in STATUS_TABS + ["all"]:
        status = "active"
    base = Challenge.objects.filter(user=request.user)
    counts = dict(base.values_list("status").annotate(n=Count("id")))
    qs = base if status == "all" else base.filter(status=status)
    category = request.GET.get("category")
    if category and category.isdigit():
        qs = qs.filter(category_id=int(category))
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    challenges = list(ProgressEngine.prefetch(qs).prefetch_related("fields"))
    results = ProgressEngine(request.user).evaluate_many(challenges)
    cards = [{"challenge": c, "progress": results[c.pk]} for c in challenges]
    return render(request, "challenges/list.html", {
        "cards": cards, "status": status, "counts": counts, "total": sum(counts.values()),
        "categories": ChallengeCategory.objects.filter(user=request.user, challenges__isnull=False).distinct(),
        "category": category, "q": q, "tabs": STATUS_TABS,
    })


@login_required
def challenge_create(request):
    template = None
    slug = request.GET.get("template")
    if slug:
        tpl = ChallengeTemplate.objects.filter(Q(owner__isnull=True) | Q(owner=request.user) | Q(is_public=True), slug=slug).first()
        if tpl:
            template = ChallengeTemplateSerializer(tpl).data
    nxt = request.GET.get("next")
    if nxt and not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = None
    return render(request, "challenges/create.html", {
        "wizard_opts": {
            "categories": _categories(request.user),
            "icons": picker_icons(),
            "colors": [c for c, _ in COLOR_CHOICES],
            "today": user_today(request.user).isoformat(),
            "template": template,
            "next": nxt,
        },
    })


def _heatmap(days, week_starts_on):
    """Group the day series into week columns with an intensity level 0..4."""
    if not days:
        return []
    by_date = {d.date: d for d in days}
    start = week_start_for(days[0].date, week_starts_on)
    end = days[-1].date
    weeks, cursor = [], start
    while cursor <= end:
        col = []
        for i in range(7):
            day = cursor + timedelta(days=i)
            p = by_date.get(day)
            level, status = 0, "none"
            if p is not None:
                status = p.status
                if p.status == "done":
                    level = 4 if (p.target and p.actual >= p.target * 1.5) else 3
                elif p.status == "partial":
                    level = 2 if (p.target and p.actual >= p.target * 0.5) else 1
            col.append({"date": day, "level": level, "status": status, "actual": p.actual if p else 0})
        weeks.append(col)
        cursor += timedelta(days=7)
    return weeks[-53:]


@login_required
def challenge_detail(request, pk):
    challenge = _owned(request, pk)
    result = ProgressEngine(request.user).evaluate(challenge, include_series=True)
    entries_qs = ChallengeEntry.objects.filter(challenge=challenge).prefetch_related("values__field").select_related("planned_activity")
    page = Paginator(entries_qs, 15).get_page(request.GET.get("page"))
    fields = [f for f in challenge.fields.all() if f.is_active]
    entries = [{"obj": e, "values": {v.field_id: v for v in e.values.all()},
                "json": {"id": e.pk, "date": e.date.isoformat(), "note": e.note, "values": {v.field.key: v.value for v in e.values.all()}}}
               for e in page]
    series = [d.as_dict() for d in result.days]
    return render(request, "challenges/detail.html", {
        "challenge": challenge,
        "p": result,
        "fields": fields,
        "fields_json": [{"key": f.key, "label": f.label, "field_type": f.field_type, "unit": f.unit, "options": f.options} for f in fields],
        "entries": entries,
        "page": page,
        "heatmap": _heatmap(result.days, request.user.profile.week_start),
        "chart_data": {"days": series, "weekly": result.statistics.get("weekly", []), "monthly": result.statistics.get("monthly", []),
                       "buckets": result.buckets, "is_duration": result.is_duration, "color": challenge.color,
                       "completed": result.completed_periods, "due": result.due_periods},
        "goals": challenge._prefetched("goals"),
        "schedules": challenge._prefetched("schedules"),
        "pauses": list(challenge.pauses.all()),
    })


@login_required
def challenge_settings(request, pk):
    challenge = _owned(request, pk)
    return render(request, "challenges/settings.html", {
        "challenge": challenge,
        "settings_opts": {
            "challenge": ChallengeSerializer(challenge, context={"request": request}).data,
            "categories": ChallengeCategorySerializer(ChallengeCategory.objects.filter(user=request.user), many=True).data,
            "icons": picker_icons(),
            "colors": [c for c, _ in COLOR_CHOICES],
            "today": user_today(request.user).isoformat(),
        },
        "milestones": list(challenge.milestones.all()),
    })


@login_required
def templates_gallery(request):
    templates = ChallengeTemplate.objects.filter(Q(owner__isnull=True) | Q(owner=request.user) | Q(is_public=True))
    return render(request, "challenges/templates.html", {"templates": templates})
