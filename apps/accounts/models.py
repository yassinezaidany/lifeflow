import zoneinfo
from datetime import time

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

TIMEZONE_CHOICES = sorted((tz, tz.replace("_", " ")) for tz in zoneinfo.available_timezones() if "/" in tz or tz == "UTC")


class User(AbstractUser):
    """Custom user: unique, case-insensitive email used as an alternative login."""

    email = models.EmailField(_("email address"), unique=True)
    is_demo = models.BooleanField(default=False, help_text=_("Created by the demo seed command."))

    REQUIRED_FIELDS = ["email"]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        return self.first_name or self.get_full_name() or self.username

    @property
    def initials(self) -> str:
        name = self.get_full_name() or self.username
        parts = [p for p in name.split() if p]
        return ("".join(p[0] for p in parts[:2]) or name[:2]).upper()


def avatar_upload_to(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"avatars/user_{instance.user_id}.{ext}"


class Profile(TimeStampedModel):
    class Theme(models.TextChoices):
        SYSTEM = "system", _("System")
        LIGHT = "light", _("Light")
        DARK = "dark", _("Dark")

    class DateFormat(models.TextChoices):
        DMY = "d/m/Y", "31/12/2026"
        MDY = "m/d/Y", "12/31/2026"
        YMD = "Y-m-d", "2026-12-31"

    class TimeFormat(models.TextChoices):
        H24 = "24h", "24h (14:30)"
        H12 = "12h", "12h (2:30 PM)"

    class WeekStart(models.IntegerChoices):
        MONDAY = 0, _("Monday")
        SUNDAY = 6, _("Sunday")
        SATURDAY = 5, _("Saturday")

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(
        upload_to=avatar_upload_to,
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    bio = models.CharField(max_length=160, blank=True)
    timezone = models.CharField(max_length=64, choices=TIMEZONE_CHOICES, default="UTC")
    language = models.CharField(max_length=8, choices=settings.LANGUAGES, default="en")
    date_format = models.CharField(max_length=8, choices=DateFormat.choices, default=DateFormat.DMY)
    time_format = models.CharField(max_length=4, choices=TimeFormat.choices, default=TimeFormat.H24)
    week_start = models.PositiveSmallIntegerField(choices=WeekStart.choices, default=WeekStart.MONDAY)
    theme = models.CharField(max_length=8, choices=Theme.choices, default=Theme.SYSTEM)
    # Planner display preferences
    planner_slot_minutes = models.PositiveSmallIntegerField(
        choices=[(15, "15 min"), (30, "30 min"), (60, "1 h")], default=30
    )
    planner_day_start = models.PositiveSmallIntegerField(default=5, help_text=_("First hour shown in the planner."))
    planner_day_end = models.PositiveSmallIntegerField(default=24, help_text=_("Last hour shown in the planner."))
    onboarding_completed = models.BooleanField(default=False)
    # Secret for the read-only iCal feed of the planner (regenerating it revokes old links).
    calendar_token = models.CharField(max_length=48, unique=True, null=True, blank=True, editable=False)

    def ensure_calendar_token(self, regenerate: bool = False) -> str:
        if regenerate or not self.calendar_token:
            import secrets

            self.calendar_token = secrets.token_urlsafe(32)
            self.save(update_fields=["calendar_token", "updated_at"])
        return self.calendar_token

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(planner_day_start__lt=models.F("planner_day_end")),
                name="profile_planner_hours_order",
            ),
            models.CheckConstraint(condition=models.Q(planner_day_end__lte=24), name="profile_planner_end_max"),
        ]

    def __str__(self) -> str:
        return f"Profile<{self.user}>"


class UserSetting(TimeStampedModel):
    """Notification preferences. Notifications are optional and off-by-default for email."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="settings")
    notifications_enabled = models.BooleanField(default=True)
    notify_activity_reminders = models.BooleanField(default=True)
    notify_daily_goals = models.BooleanField(default=True)
    notify_end_of_day = models.BooleanField(default=True)
    notify_weekly_review = models.BooleanField(default=True)
    notify_report_ready = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=False)
    push_notifications = models.BooleanField(default=True, help_text=_("Send to devices where push is enabled."))
    morning_summary_time = models.TimeField(default=time(8, 0))
    end_of_day_time = models.TimeField(default=time(21, 0))

    def __str__(self) -> str:
        return f"Settings<{self.user}>"
