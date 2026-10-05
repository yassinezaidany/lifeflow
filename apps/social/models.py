"""
Social layer — privacy first.

* Friendships are explicit (request → accept). There is no user directory and no feed.
* A shared challenge is a common *definition* (fields, goal, schedule, period). Each
  member gets a personal copy of the challenge: entries stay private and personal.
* The leaderboard only exposes aggregate figures (progress %, completion rate,
  streak, status) and each member can hide them.
"""
import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.challenges.models import COLOR_CHOICES, Challenge
from apps.core.models import TimeStampedModel


class Friendship(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACCEPTED = "accepted", _("Accepted")
        DECLINED = "declined", _("Declined")

    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friend_requests_sent")
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friend_requests_received")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["from_user", "to_user"], name="uniq_friend_request"),
            models.CheckConstraint(condition=~Q(from_user=models.F("to_user")), name="no_self_friendship"),
        ]
        indexes = [models.Index(fields=["to_user", "status"]), models.Index(fields=["from_user", "status"])]

    def __str__(self) -> str:
        return f"{self.from_user_id}→{self.to_user_id} {self.status}"

    def other(self, user):
        return self.to_user if self.from_user_id == user.pk else self.from_user


def new_invite_code() -> str:
    return secrets.token_urlsafe(9)


class SharedChallenge(TimeStampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_shared_challenges")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, max_length=2000)
    icon = models.CharField(max_length=40, default="target")
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default="indigo")
    definition = models.JSONField(default=dict, help_text=_("Wizard payload: fields, goal, schedule."))
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    invite_code = models.CharField(max_length=24, unique=True, default=new_invite_code)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class SharedChallengeMember(TimeStampedModel):
    class Status(models.TextChoices):
        INVITED = "invited", _("Invited")
        ACTIVE = "active", _("Member")
        LEFT = "left", _("Left")

    shared = models.ForeignKey(SharedChallenge, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shared_memberships")
    challenge = models.ForeignKey(Challenge, on_delete=models.SET_NULL, null=True, blank=True, related_name="shared_memberships",
                                  help_text=_("The member's personal copy (private entries)."))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.INVITED)
    share_progress = models.BooleanField(default=True, help_text=_("Show my progress in the group leaderboard."))
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    joined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["shared", "user"], name="uniq_shared_member")]
        indexes = [models.Index(fields=["user", "status"])]

    def __str__(self) -> str:
        return f"{self.user_id}@{self.shared_id} {self.status}"
