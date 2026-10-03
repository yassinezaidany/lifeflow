from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    class Kind(models.TextChoices):
        ACTIVITY_REMINDER = "activity_reminder", _("Activity reminder")
        CHALLENGE_REMINDER = "challenge_reminder", _("Challenge reminder")
        DAILY_GOAL = "daily_goal", _("Daily goal")
        END_OF_DAY = "end_of_day", _("End of day")
        WEEKLY_REVIEW = "weekly_review", _("Weekly review")
        REPORT_READY = "report_ready", _("Report ready")
        MILESTONE = "milestone", _("Milestone reached")
        SYSTEM = "system", _("System")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField(max_length=140)
    body = models.CharField(max_length=500, blank=True)
    url = models.CharField(max_length=300, blank=True)
    # NULL for ad-hoc notifications (MySQL allows several NULLs in a unique index).
    dedupe_key = models.CharField(max_length=120, null=True, blank=True, help_text=_("Prevents sending the same reminder twice."))
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read", "-created_at"])]
        constraints = [models.UniqueConstraint(fields=["user", "dedupe_key"], name="uniq_notification_dedupe")]

    def __str__(self) -> str:
        return self.title
