"""
Planner data model.

Recurring activities are stored once as a `RecurringRule`. Concrete
`PlannedActivity` rows are materialised lazily, only for the dates that are
displayed or evaluated (see services.occurrences). Each occurrence is unique per
(rule, occurrence_date), so rules are never duplicated and an occurrence can be
edited/completed individually (it then becomes "detached" from the rule).
"""
from __future__ import annotations

from datetime import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.challenges.models import COLOR_CHOICES, Challenge
from apps.core.dates import minutes_between
from apps.core.models import OwnedModel, TimeStampedModel

MIDNIGHT = time(0, 0)


class Priority(models.TextChoices):
    LOW = "low", _("Low")
    MEDIUM = "medium", _("Medium")
    HIGH = "high", _("High")


def time_range_constraint(name: str) -> models.CheckConstraint:
    # end must be after start; 00:00 as end time means "until midnight".
    return models.CheckConstraint(condition=Q(end_time__gt=F("start_time")) | Q(end_time=MIDNIGHT), name=name)


def validate_time_range(start, end):
    if start is None or end is None:
        return
    if not (end > start or end == MIDNIGHT):
        raise ValidationError({"end_time": _("End time must be after start time.")})


class ActivityCategory(OwnedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity_categories")
    name = models.CharField(max_length=60)
    icon = models.CharField(max_length=40, default="circle")
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default="slate")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "activity categories"
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="uniq_activity_category_per_user")]

    def __str__(self) -> str:
        return self.name


class TimedItem(models.Model):
    title = models.CharField(max_length=120)
    start_time = models.TimeField()
    end_time = models.TimeField()
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, blank=True)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.MEDIUM)
    notes = models.TextField(blank=True, max_length=2000)

    class Meta:
        abstract = True

    @property
    def duration_minutes(self) -> int:
        return minutes_between(self.start_time, self.end_time)

    def clean(self):
        validate_time_range(self.start_time, self.end_time)


class RecurringRule(OwnedModel, TimedItem):
    class Frequency(models.TextChoices):
        DAILY = "daily", _("Every day")
        WEEKLY = "weekly", _("Selected days")
        INTERVAL = "interval", _("Every N days")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recurring_rules")
    description = models.TextField(blank=True, max_length=2000)
    category = models.ForeignKey(ActivityCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="rules")
    challenge = models.ForeignKey(Challenge, on_delete=models.SET_NULL, null=True, blank=True, related_name="recurring_rules")
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.WEEKLY)
    weekdays = models.JSONField(default=list, blank=True, help_text=_("0 = Monday … 6 = Sunday"))
    interval_days = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["start_time"]
        indexes = [models.Index(fields=["user", "is_active"])]
        constraints = [
            time_range_constraint("rule_time_range"),
            models.CheckConstraint(condition=Q(interval_days__gte=1), name="rule_interval_positive"),
            models.CheckConstraint(condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")), name="rule_date_range"),
        ]

    def __str__(self) -> str:
        return f"Rule<{self.title}>"

    def occurs_on(self, day) -> bool:
        if not self.is_active or day < self.start_date or (self.end_date and day > self.end_date):
            return False
        if self.frequency == self.Frequency.DAILY:
            return True
        if self.frequency == self.Frequency.WEEKLY:
            return day.weekday() in (self.weekdays or [])
        return (day - self.start_date).days % max(self.interval_days, 1) == 0

    def clean(self):
        super().clean()
        if self.frequency == self.Frequency.WEEKLY:
            days = self.weekdays or []
            if not days or any(not isinstance(d, int) or not 0 <= d <= 6 for d in days):
                raise ValidationError({"weekdays": _("Select at least one day of the week.")})
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("End date must be on or after the start date.")})


class PlannedActivity(OwnedModel, TimedItem):
    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        IN_PROGRESS = "in_progress", _("In progress")
        COMPLETED = "completed", _("Completed")
        PARTIALLY_COMPLETED = "partial", _("Partially completed")
        MISSED = "missed", _("Missed")
        CANCELLED = "cancelled", _("Cancelled")
        RESCHEDULED = "rescheduled", _("Rescheduled")

    DONE_STATUSES = {Status.COMPLETED, Status.PARTIALLY_COMPLETED}
    CLOSED_STATUSES = DONE_STATUSES | {Status.MISSED, Status.CANCELLED, Status.RESCHEDULED}

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="planned_activities")
    description = models.TextField(blank=True, max_length=2000)
    date = models.DateField()
    category = models.ForeignKey(ActivityCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="activities")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    challenge = models.ForeignKey(Challenge, on_delete=models.SET_NULL, null=True, blank=True, related_name="planned_activities")
    recurring_rule = models.ForeignKey(RecurringRule, on_delete=models.SET_NULL, null=True, blank=True, related_name="occurrences")
    occurrence_date = models.DateField(null=True, blank=True)
    is_detached = models.BooleanField(default=False, help_text=_("Edited individually; no longer follows its rule."))
    rescheduled_from = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="rescheduled_to")
    actual_minutes = models.PositiveIntegerField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["date", "start_time"]
        verbose_name_plural = "planned activities"
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["challenge", "date"]),
        ]
        constraints = [
            time_range_constraint("activity_time_range"),
            models.UniqueConstraint(fields=["recurring_rule", "occurrence_date"], name="uniq_rule_occurrence"),
        ]

    def __str__(self) -> str:
        return f"{self.date} {self.start_time:%H:%M} {self.title}"

    @property
    def effective_color(self) -> str:
        return self.color or (self.category.color if self.category_id and self.category else "slate")

    @property
    def is_done(self) -> bool:
        return self.status in self.DONE_STATUSES


class PlannerTemplate(OwnedModel):
    """A reusable day layout (University day, Weekend, Ramadan day...)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="planner_templates")
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=255, blank=True)
    icon = models.CharField(max_length=40, default="layout-template")
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default="indigo")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="uniq_planner_template_per_user")]

    def __str__(self) -> str:
        return self.name


class PlannerTemplateItem(TimedItem, TimeStampedModel):
    template = models.ForeignKey(PlannerTemplate, on_delete=models.CASCADE, related_name="items")
    category = models.ForeignKey(ActivityCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    challenge = models.ForeignKey(Challenge, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["start_time"]
        constraints = [time_range_constraint("template_item_time_range")]
