"""
Generic challenge engine data model.

Nothing here knows about "Sport", "Qur'an" or any specific activity: a challenge is
a set of user-defined *tracking fields*, a versioned *goal* (what counts and how
much) and a versioned *schedule* (which days are active).
"""
from __future__ import annotations

from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import OwnedModel, TimeStampedModel

COLOR_CHOICES = [
    ("slate", _("Slate")),
    ("indigo", _("Indigo")),
    ("blue", _("Blue")),
    ("sky", _("Sky")),
    ("teal", _("Teal")),
    ("emerald", _("Emerald")),
    ("lime", _("Lime")),
    ("amber", _("Amber")),
    ("orange", _("Orange")),
    ("rose", _("Rose")),
    ("pink", _("Pink")),
    ("violet", _("Violet")),
]


class ChallengeCategory(OwnedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="challenge_categories")
    name = models.CharField(max_length=60)
    icon = models.CharField(max_length=40, default="tag")
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default="slate")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "challenge categories"
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="uniq_challenge_category_per_user")]

    def __str__(self) -> str:
        return self.name


class ChallengeTemplate(TimeStampedModel):
    """Reusable blueprint. `owner=None` means a system template available to everyone.

    `definition` holds the wizard payload (fields, goal, schedule) so a template can
    pre-fill the creation wizard and remain editable before creation.
    """

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="challenge_templates")
    slug = models.SlugField(max_length=80)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=40, default="target")
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default="indigo")
    category_name = models.CharField(max_length=60, blank=True)
    duration_days = models.PositiveIntegerField(null=True, blank=True)
    definition = models.JSONField(default=dict)
    is_public = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        constraints = [models.UniqueConstraint(fields=["owner", "slug"], name="uniq_template_slug_per_owner")]

    def __str__(self) -> str:
        return self.name


class Challenge(OwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        PAUSED = "paused", _("Paused")
        COMPLETED = "completed", _("Completed")
        ARCHIVED = "archived", _("Archived")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="challenges")
    category = models.ForeignKey(ChallengeCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="challenges")
    template = models.ForeignKey(ChallengeTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="challenges")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, max_length=2000)
    icon = models.CharField(max_length=40, default="target")
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default="indigo")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text=_("Leave empty for an open-ended challenge."))
    closed_on = models.DateField(null=True, blank=True, help_text=_("Date the challenge was completed/archived early."))
    reminder_time = models.TimeField(null=True, blank=True, help_text=_("Daily reminder on active days, if not done yet."))
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "start_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="challenge_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("End date must be on or after the start date.")})

    # --- versioned configuration helpers -------------------------------------------------
    def goal_on(self, day: date) -> "Goal | None":
        return _version_on(self._prefetched("goals"), day)

    def schedule_on(self, day: date) -> "Schedule | None":
        return _version_on(self._prefetched("schedules"), day)

    @property
    def current_goal(self) -> "Goal | None":
        goals = self._prefetched("goals")
        return next((g for g in goals if g.effective_to is None), goals[-1] if goals else None)

    @property
    def current_schedule(self) -> "Schedule | None":
        schedules = self._prefetched("schedules")
        return next((s for s in schedules if s.effective_to is None), schedules[-1] if schedules else None)

    def _prefetched(self, name: str) -> list:
        cache = getattr(self, "_prefetched_objects_cache", {})
        items = list(cache[name]) if name in cache else list(getattr(self, name).all())
        return sorted(items, key=lambda v: (v.effective_from, v.pk or 0))

    @property
    def active_fields(self):
        return [f for f in self.fields.all() if f.is_active]


def _version_on(versions: list, day: date):
    found = None
    for v in versions:
        if v.effective_from <= day and (v.effective_to is None or day <= v.effective_to):
            found = v
    return found


class TrackingField(TimeStampedModel):
    """A user-defined piece of data recorded on each entry (pages, duration, type...)."""

    class FieldType(models.TextChoices):
        BOOLEAN = "boolean", _("Done / Not done")
        INTEGER = "integer", _("Whole number")
        DECIMAL = "decimal", _("Decimal number")
        DURATION = "duration", _("Duration (minutes)")
        TIME = "time", _("Time of day")
        TEXT = "text", _("Text")
        SELECT = "select", _("Choice list")

    NUMERIC_TYPES = {FieldType.INTEGER, FieldType.DECIMAL, FieldType.DURATION}
    MEASURABLE_TYPES = NUMERIC_TYPES | {FieldType.BOOLEAN, FieldType.TIME}  # time: with a before/after threshold

    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="fields")
    key = models.SlugField(max_length=40)
    label = models.CharField(max_length=60)
    field_type = models.CharField(max_length=12, choices=FieldType.choices)
    unit = models.CharField(max_length=20, blank=True)
    options = models.JSONField(default=list, blank=True, help_text=_("Choices for select fields."))
    required = models.BooleanField(default=False)
    min_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True, help_text=_("Inactive fields keep their history but are hidden from forms."))

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["challenge", "key"], name="uniq_field_key_per_challenge")]

    def __str__(self) -> str:
        return f"{self.challenge_id}:{self.label}"

    @property
    def is_measurable(self) -> bool:
        return self.field_type in self.MEASURABLE_TYPES

    @property
    def display_unit(self) -> str:
        if self.field_type == self.FieldType.DURATION:
            return "min"
        return self.unit

    def clean(self):
        if self.field_type == self.FieldType.SELECT and not self.options:
            raise ValidationError({"options": _("A choice field needs at least one option.")})
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValidationError({"max_value": _("Maximum must be greater than minimum.")})


class VersionedConfig(TimeStampedModel):
    """Goals and schedules are versioned: editing one closes the current version and
    opens a new one so that past days keep being evaluated with the rules in force
    at that time (no silent rewriting of history)."""

    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        abstract = True


class Goal(VersionedConfig):
    class Period(models.TextChoices):
        DAILY = "daily", _("per day")
        WEEKLY = "weekly", _("per week")
        MONTHLY = "monthly", _("per month")
        TOTAL = "total", _("in total")

    class Aggregation(models.TextChoices):
        SUM = "sum", _("Sum of the measured value")
        COUNT = "count", _("Number of qualifying entries")

    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="goals")
    metric = models.ForeignKey(
        # RESTRICT: a field used by a goal can't be deleted on its own (it is archived instead),
        # but deleting the whole challenge cascades normally.
        TrackingField, on_delete=models.RESTRICT, null=True, blank=True, related_name="goals",
        help_text=_("Field that is measured. Empty = count entries (sessions)."),
    )
    period = models.CharField(max_length=10, choices=Period.choices, default=Period.DAILY)
    aggregation = models.CharField(max_length=8, choices=Aggregation.choices, default=Aggregation.SUM)
    target = models.DecimalField(max_digits=12, decimal_places=2)
    min_per_entry = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text=_("Minimum value for an entry to count (e.g. at least 30 minutes)."),
    )
    class Direction(models.TextChoices):
        AT_LEAST = "at_least", _("at least")
        AT_MOST = "at_most", _("at most")

    # AT_MOST = limit goal ("at most 2 h of screen time per day"): a period succeeds
    # while its total stays under the target.
    direction = models.CharField(max_length=8, choices=Direction.choices, default=Direction.AT_LEAST)
    # Time-of-day goals (metric is a "time" field): an entry counts when the recorded
    # time is before / after the threshold, e.g. "wake up before 05:30".
    time_comparison = models.CharField(max_length=6, choices=[("before", _("before")), ("after", _("after"))], blank=True)
    time_threshold = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["effective_from", "id"]
        indexes = [models.Index(fields=["challenge", "effective_from"])]
        constraints = [
            models.CheckConstraint(condition=Q(target__gt=0), name="goal_target_positive"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="goal_effective_range",
            ),
            models.CheckConstraint(condition=Q(min_per_entry__isnull=True) | Q(min_per_entry__gte=0), name="goal_min_per_entry_positive"),
        ]

    def __str__(self) -> str:
        return f"Goal<{self.challenge_id} {self.target} {self.period}>"

    @property
    def is_limit(self) -> bool:
        return self.direction == self.Direction.AT_MOST

    @property
    def is_time_goal(self) -> bool:
        return self.metric is not None and self.metric.field_type == TrackingField.FieldType.TIME

    @property
    def unit_label(self) -> str:
        if self.metric is None:
            return str(_("sessions"))
        if self.metric.field_type in (TrackingField.FieldType.BOOLEAN, TrackingField.FieldType.TIME):
            return str(_("days"))
        if self.aggregation == self.Aggregation.COUNT:
            return str(_("sessions"))
        return self.metric.display_unit

    @property
    def is_duration(self) -> bool:
        return (
            self.metric is not None
            and self.metric.field_type == TrackingField.FieldType.DURATION
            and self.aggregation == self.Aggregation.SUM
        )


class Schedule(VersionedConfig):
    class Frequency(models.TextChoices):
        DAILY = "daily", _("Every day")
        WEEKDAYS = "weekdays", _("Selected days of the week")
        INTERVAL = "interval", _("Every N days")

    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="schedules")
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.DAILY)
    weekdays = models.JSONField(default=list, blank=True, help_text=_("0 = Monday … 6 = Sunday"))
    interval_days = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["effective_from", "id"]
        indexes = [models.Index(fields=["challenge", "effective_from"])]
        constraints = [
            models.CheckConstraint(condition=Q(interval_days__gte=1), name="schedule_interval_positive"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="schedule_effective_range",
            ),
        ]

    def __str__(self) -> str:
        return f"Schedule<{self.challenge_id} {self.frequency}>"

    def is_scheduled(self, day: date) -> bool:
        if self.frequency == self.Frequency.DAILY:
            return True
        if self.frequency == self.Frequency.WEEKDAYS:
            return day.weekday() in (self.weekdays or [])
        return (day - self.effective_from).days % max(self.interval_days, 1) == 0

    def clean(self):
        if self.frequency == self.Frequency.WEEKDAYS:
            days = self.weekdays or []
            if not days or any(not isinstance(d, int) or d < 0 or d > 6 for d in days):
                raise ValidationError({"weekdays": _("Select at least one valid day of the week.")})


class ChallengePause(TimeStampedModel):
    """A paused period is neither a success nor a failure: it is excluded from evaluation."""

    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="pauses")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="pause_end_after_start",
            ),
        ]

    def covers(self, day: date, today: date | None = None) -> bool:
        end = self.end_date or today or day
        return self.start_date <= day <= end


class RestDay(OwnedModel):
    """A planned rest day. `challenge=None` means a rest day for all challenges."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rest_days")
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, null=True, blank=True, related_name="rest_days")
    date = models.DateField()
    note = models.CharField(max_length=140, blank=True)

    class Meta:
        ordering = ["date"]
        indexes = [models.Index(fields=["user", "date"])]
        constraints = [models.UniqueConstraint(fields=["user", "challenge", "date"], name="uniq_rest_day")]

    def __str__(self) -> str:
        return f"Rest<{self.date} {self.challenge_id or 'all'}>"


class Milestone(TimeStampedModel):
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=80)
    target_value = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["target_value"]
        constraints = [models.CheckConstraint(condition=Q(target_value__gt=0), name="milestone_target_positive")]

    def __str__(self) -> str:
        return self.title
