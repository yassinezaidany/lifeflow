from django.http import HttpResponse
from django.utils.translation import gettext as _
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.api.mixins import OwnedQuerysetMixin
from apps.core.dates import user_today

from .generators.pdf import render_monthly_report_pdf
from .models import MonthlyReport, ReportChallengeSnapshot
from .services.monthly import generate_monthly_report


class SnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportChallengeSnapshot
        exclude = ["report"]


class MonthlyReportSerializer(serializers.ModelSerializer):
    challenges = SnapshotSerializer(many=True, read_only=True)

    class Meta:
        model = MonthlyReport
        fields = ["id", "year", "month", "version", "period_start", "period_end", "generated_at", "user_display_name",
                  "timezone", "summary", "planner", "challenges"]


class MonthlyReportListSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyReport
        fields = ["id", "year", "month", "version", "period_start", "period_end", "generated_at", "summary"]


class ReportViewSet(OwnedQuerysetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = MonthlyReport.objects.prefetch_related("challenges")

    def get_serializer_class(self):
        return MonthlyReportListSerializer if self.action == "list" else MonthlyReportSerializer

    @action(detail=False, methods=["post"])
    def monthly(self, request):
        today = user_today(request.user)
        try:
            year = int(request.data.get("year") or today.year)
            month = int(request.data.get("month") or today.month)
        except (TypeError, ValueError):
            raise ValidationError({"month": _("Invalid month.")})
        if not (2000 <= year <= 2100):
            raise ValidationError({"year": _("Invalid year.")})
        report = generate_monthly_report(request.user, year, month)
        report = self.get_queryset().get(pk=report.pk)
        return Response(MonthlyReportSerializer(report).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        return pdf_response(self.get_object(), inline=request.query_params.get("inline") == "1")


def pdf_response(report: MonthlyReport, inline: bool = False) -> HttpResponse:
    response = HttpResponse(render_monthly_report_pdf(report), content_type="application/pdf")
    name = f"lifeflow-report-{report.year}-{report.month:02d}" + (f"-v{report.version}" if report.version > 1 else "") + ".pdf"
    response["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{name}"'
    return response
