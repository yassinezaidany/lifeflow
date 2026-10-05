from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.challenges.models import Challenge
from apps.core.dates import user_today

from .api import pdf_response
from .exports import export_csv, export_xlsx
from .models import MonthlyReport
from .services.monthly import generate_monthly_report


def _month_choices(user, count=12):
    today = user_today(user)
    y, m = today.year, today.month
    out = []
    for _i in range(count):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


@login_required
def report_list(request):
    reports = MonthlyReport.objects.filter(user=request.user)
    return render(request, "reports/list.html", {
        "reports": reports, "months": _month_choices(request.user),
        "challenges": Challenge.objects.filter(user=request.user).only("id", "name"),
    })


@login_required
@require_POST
def generate(request):
    try:
        year, month = (int(x) for x in request.POST.get("month", "").split("-"))
        report = generate_monthly_report(request.user, year, month)
    except (ValueError, TypeError):
        messages.error(request, _("Choose a valid month."))
        return redirect("reports:list")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("reports:list")
    messages.success(request, _("Report generated."))
    return redirect("reports:detail", pk=report.pk)


@login_required
def report_detail(request, pk):
    report = get_object_or_404(MonthlyReport.objects.prefetch_related("challenges"), pk=pk, user=request.user)
    return render(request, "reports/detail.html", {"report": report, "snapshots": list(report.challenges.all())})


@login_required
def report_pdf(request, pk):
    report = get_object_or_404(MonthlyReport.objects.prefetch_related("challenges"), pk=pk, user=request.user)
    return pdf_response(report, inline=request.GET.get("inline") == "1")


@login_required
@require_POST
def report_delete(request, pk):
    get_object_or_404(MonthlyReport, pk=pk, user=request.user).delete()
    messages.success(request, _("Report deleted."))
    return redirect("reports:list")


@login_required
def import_entries(request):
    from .imports import import_entries_csv

    report = None
    if request.method == "POST":
        uploaded = request.FILES.get("file")
        if not uploaded:
            messages.error(request, _("Choose a CSV file."))
        else:
            try:
                report = import_entries_csv(request.user, uploaded)
                if report.created:
                    messages.success(request, _("%(n)s entries imported.") % {"n": report.created})
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
    return render(request, "reports/import.html", {"report": report})


@login_required
def export(request):
    fmt = request.GET.get("format", "csv")
    if fmt == "xlsx":
        return export_xlsx(request.user)
    kind = "statistics" if request.GET.get("kind") == "statistics" else "entries"
    challenge = None
    if request.GET.get("challenge", "").isdigit():
        challenge = get_object_or_404(Challenge, pk=int(request.GET["challenge"]), user=request.user)
    return export_csv(request.user, kind, challenge)
