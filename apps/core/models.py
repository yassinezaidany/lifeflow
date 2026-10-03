from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OwnedModel(TimeStampedModel):
    """Every user-owned record carries a direct FK to its owner.

    Even when ownership could be derived through a parent (e.g. entry -> challenge),
    the denormalised `user` column makes ownership checks a single indexed filter
    and keeps data isolation trivially auditable.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """Traceability of important business operations (not every UI interaction)."""

    class Action(models.TextChoices):
        CHALLENGE_CREATED = "challenge_created", _("Challenge created")
        CHALLENGE_UPDATED = "challenge_updated", _("Challenge updated")
        CHALLENGE_STATUS = "challenge_status", _("Challenge status changed")
        CHALLENGE_DELETED = "challenge_deleted", _("Challenge deleted")
        GOAL_CHANGED = "goal_changed", _("Goal changed")
        SCHEDULE_CHANGED = "schedule_changed", _("Schedule changed")
        ENTRY_CREATED = "entry_created", _("Entry created")
        ENTRY_UPDATED = "entry_updated", _("Entry modified")
        ENTRY_DELETED = "entry_deleted", _("Entry deleted")
        ACTIVITY_CREATED = "activity_created", _("Planner activity created")
        ACTIVITY_UPDATED = "activity_updated", _("Planner activity modified")
        ACTIVITY_STATUS = "activity_status", _("Planner activity status changed")
        ACTIVITY_DELETED = "activity_deleted", _("Planner activity deleted")
        RULE_CHANGED = "rule_changed", _("Recurring rule changed")
        TEMPLATE_APPLIED = "template_applied", _("Day template applied")
        REPORT_GENERATED = "report_generated", _("Report generated")
        ACCOUNT = "account", _("Account event")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=40, choices=Action.choices)
    object_type = models.CharField(max_length=60, blank=True)
    object_id = models.CharField(max_length=40, blank=True)
    description = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.user_id} {self.action} {self.object_type}#{self.object_id}"
