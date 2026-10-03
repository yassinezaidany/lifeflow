from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.challenges.models import Challenge
from apps.core.models import OwnedModel


class JournalEntry(OwnedModel):
    class Scope(models.TextChoices):
        DAY = "day", _("Day")
        WEEK = "week", _("Week")
        MONTH = "month", _("Month")
        CHALLENGE = "challenge", _("Challenge")

    class Mood(models.IntegerChoices):
        AWFUL = 1, "😞"
        BAD = 2, "😕"
        OK = 3, "😐"
        GOOD = 4, "🙂"
        GREAT = 5, "😄"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="journal_entries")
    date = models.DateField()
    scope = models.CharField(max_length=10, choices=Scope.choices, default=Scope.DAY)
    challenge = models.ForeignKey(Challenge, on_delete=models.SET_NULL, null=True, blank=True, related_name="journal_entries")
    title = models.CharField(max_length=140, blank=True)
    content = models.TextField(max_length=20000)
    mood = models.PositiveSmallIntegerField(choices=Mood.choices, null=True, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name_plural = "journal entries"
        indexes = [models.Index(fields=["user", "date"])]
        constraints = [models.CheckConstraint(condition=Q(mood__isnull=True) | Q(mood__gte=1, mood__lte=5), name="journal_mood_range")]

    def __str__(self) -> str:
        return self.title or f"Journal {self.date}"


class WeeklyReview(OwnedModel):
    """Reflection attached to a week (keyed by the week's first day)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="weekly_reviews")
    week_start = models.DateField()
    went_well = models.TextField(blank=True, max_length=5000)
    difficult = models.TextField(blank=True, max_length=5000)
    improve = models.TextField(blank=True, max_length=5000)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-week_start"]
        constraints = [
            models.UniqueConstraint(fields=["user", "week_start"], name="uniq_weekly_review"),
            models.CheckConstraint(condition=Q(rating__isnull=True) | Q(rating__gte=1, rating__lte=5), name="weekly_review_rating_range"),
        ]

    def __str__(self) -> str:
        return f"Review {self.week_start}"
