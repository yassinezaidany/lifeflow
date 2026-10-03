"""
Monthly reports are immutable snapshots: every number is copied at generation
time, so editing entries or deleting a challenge later never changes an old report.
Regenerating a month creates a new version instead of overwriting.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.challenges.models import Challenge
from apps.core.models import OwnedModel


class MonthlyReport(OwnedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="monthly_reports")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    version = models.PositiveSmallIntegerField(default=1)
    period_start = models.DateField()
    period_end = models.DateField()
    generated_at = models.DateTimeField()
    user_display_name = models.CharField(max_length=150)
    timezone = models.CharField(max_length=64)
    summary = models.JSONField(default=dict)
    planner = models.JSONField(default=dict)

    class Meta:
        ordering = ["-year", "-month", "-version"]
        indexes = [models.Index(fields=["user", "year", "month"])]
        constraints = [
            models.UniqueConstraint(fields=["user", "year", "month", "version"], name="uniq_report_version"),
            models.CheckConstraint(condition=Q(month__gte=1, month__lte=12), name="report_month_range"),
        ]

    def __str__(self) -> str:
        return f"Report {self.year}-{self.month:02d} v{self.version}"


class ReportChallengeSnapshot(models.Model):
    report = models.ForeignKey(MonthlyReport, on_delete=models.CASCADE, related_name="challenges")
    challenge = models.ForeignKey(Challenge, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=60, blank=True)
    color = models.CharField(max_length=20, default="indigo")
    goal_description = models.CharField(max_length=160)
    unit = models.CharField(max_length=30, blank=True)
    is_duration = models.BooleanField(default=False)
    goal = models.FloatField(default=0)
    actual = models.FloatField(default=0)
    expected = models.FloatField(null=True, blank=True)
    progress = models.FloatField(null=True, blank=True)
    gap = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20)
    completion_rate = models.FloatField(null=True, blank=True)
    current_streak = models.PositiveIntegerField(default=0)
    best_streak = models.PositiveIntegerField(default=0)
    streak_unit = models.CharField(max_length=10, blank=True)
    average = models.FloatField(null=True, blank=True)
    active_days = models.PositiveIntegerField(default=0)
    completed_periods = models.PositiveIntegerField(default=0)
    due_periods = models.PositiveIntegerField(default=0)
    daily_series = models.JSONField(default=list)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.report_id}:{self.name}"
