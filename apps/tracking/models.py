from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.challenges.models import Challenge, TrackingField
from apps.core.models import OwnedModel


class ChallengeEntry(OwnedModel):
    """One real result recorded by the user. A day may hold several entries."""

    class Source(models.TextChoices):
        MANUAL = "manual", _("Manual")
        PLANNER = "planner", _("From planner")
        QUICK_ADD = "quick_add", _("Quick add")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entries")
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="entries")
    date = models.DateField()
    note = models.TextField(blank=True, max_length=2000)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL)
    planned_activity = models.ForeignKey(
        "planner.PlannedActivity", on_delete=models.SET_NULL, null=True, blank=True, related_name="entries"
    )

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name_plural = "challenge entries"
        indexes = [
            models.Index(fields=["challenge", "date"]),
            models.Index(fields=["user", "date"]),
        ]

    def __str__(self) -> str:
        return f"Entry<{self.challenge_id} {self.date}>"


class EntryFieldValue(models.Model):
    """Typed storage of one field value. Exactly one value column is used per type:
    number (integer/decimal/duration-in-minutes), boolean, time, or text (text/select)."""

    entry = models.ForeignKey(ChallengeEntry, on_delete=models.CASCADE, related_name="values")
    field = models.ForeignKey(TrackingField, on_delete=models.CASCADE, related_name="values")
    value_number = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)
    value_time = models.TimeField(null=True, blank=True)
    value_text = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["entry", "field"], name="uniq_value_per_entry_field")]
        indexes = [models.Index(fields=["field", "entry"])]

    def __str__(self) -> str:
        return f"{self.field_id}={self.value}"

    @property
    def value(self):
        ft = self.field.field_type
        T = TrackingField.FieldType
        if ft == T.BOOLEAN:
            return self.value_bool
        if ft in (T.INTEGER, T.DURATION):
            return int(self.value_number) if self.value_number is not None else None
        if ft == T.DECIMAL:
            return float(self.value_number) if self.value_number is not None else None
        if ft == T.TIME:
            return self.value_time.strftime("%H:%M") if self.value_time else None
        return self.value_text or None
