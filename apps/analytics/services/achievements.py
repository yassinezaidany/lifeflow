"""Achievements (badges), computed on the fly from the user's real data.

Nothing is stored: a badge is earned as long as the data that justifies it exists, so badges
can never drift from reality (deleting entries can take a badge away again). Planned
activities only count once the user confirmed them (planner ≠ success).
"""
from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

from apps.challenges.models import Challenge
from apps.journal.models import JournalEntry, WeeklyReview
from apps.planner.models import PlannedActivity
from apps.tracking.models import ChallengeEntry

from .progress import ProgressEngine


@dataclass
class Achievement:
    key: str
    icon: str
    title: str
    description: str
    value: int
    target: int
    group: str

    @property
    def earned(self) -> bool:
        return self.value >= self.target

    @property
    def percent(self) -> int:
        return min(round(self.value / self.target * 100), 100) if self.target else 100


# (key, icon, title, description, metric, target, group)
DEFINITIONS = [
    ("first-step", "check", _("First step"), _("Record your first result."), "entries", 1, "consistency"),
    ("regular", "list-checks", _("Regular"), _("Record 50 results."), "entries", 50, "consistency"),
    ("centurion", "medal", _("Centurion"), _("Record 250 results."), "entries", 250, "consistency"),
    ("active-days-30", "calendar-check", _("A month of effort"), _("Record something on 30 different days."), "active_days", 30, "consistency"),
    ("streak-7", "flame", _("One week strong"), _("Reach a 7-day streak on a daily challenge."), "daily_streak", 7, "streaks"),
    ("streak-30", "flame", _("Unstoppable"), _("Reach a 30-day streak on a daily challenge."), "daily_streak", 30, "streaks"),
    ("weeks-8", "repeat", _("Steady rhythm"), _("Keep a weekly goal 8 weeks in a row."), "weekly_streak", 8, "streaks"),
    ("limit-14", "shield-check", _("Self-control"), _("Stay under a limit 14 periods in a row."), "limit_streak", 14, "streaks"),
    ("finisher", "trophy", _("Finisher"), _("Complete a challenge."), "completed", 1, "challenges"),
    ("milestone", "star", _("Milestone"), _("Reach a challenge milestone."), "milestones", 1, "challenges"),
    ("explorer", "layers", _("Explorer"), _("Run 3 challenges at the same time."), "active_challenges", 3, "challenges"),
    ("planner-10", "calendar-days", _("Planner"), _("Complete 10 planned activities."), "planned_done", 10, "planner"),
    ("planner-100", "calendar-range", _("Master planner"), _("Complete 100 planned activities."), "planned_done", 100, "planner"),
    ("journal-7", "notebook-pen", _("Reflective"), _("Write 7 journal entries."), "journal", 7, "reflection"),
    ("review-4", "list-checks", _("Looking back"), _("Complete 4 weekly reviews."), "reviews", 4, "reflection"),
]

GROUPS = [
    ("consistency", _("Consistency")),
    ("streaks", _("Streaks")),
    ("challenges", _("Challenges")),
    ("planner", _("Planner")),
    ("reflection", _("Reflection")),
]


def _metrics(user) -> dict[str, int]:
    entries = ChallengeEntry.objects.filter(user=user)
    challenges = list(ProgressEngine.prefetch(Challenge.objects.filter(user=user)))
    results = ProgressEngine(user).evaluate_many(challenges) if challenges else {}
    streak = {"day": 0, "week": 0, "limit": 0}
    completed = milestones = 0
    for c in challenges:
        r = results[c.pk]
        if r.goal_obj is None:
            continue
        if r.goal_obj.is_limit:
            streak["limit"] = max(streak["limit"], r.best_streak)
        elif r.streak_unit in streak:
            streak[r.streak_unit] = max(streak[r.streak_unit], r.best_streak)
        if c.status == Challenge.Status.COMPLETED or (r.progress is not None and r.progress >= 100 and not r.goal_obj.is_limit
                                                       and c.end_date is not None and r.window[1] >= c.end_date):
            completed += 1
        milestones += sum(1 for m in r.milestones if m["reached"])
    return {
        "entries": entries.count(),
        "active_days": entries.values("date").distinct().count(),
        "daily_streak": streak["day"],
        "weekly_streak": streak["week"],
        "limit_streak": streak["limit"],
        "completed": completed,
        "milestones": milestones,
        "active_challenges": sum(1 for c in challenges if c.status == Challenge.Status.ACTIVE),
        "planned_done": PlannedActivity.objects.filter(user=user, status__in=PlannedActivity.DONE_STATUSES).count(),
        "journal": JournalEntry.objects.filter(user=user).count(),
        "reviews": WeeklyReview.objects.filter(user=user).count(),
    }


def build_achievements(user) -> dict:
    metrics = _metrics(user)
    items = [Achievement(key, icon, str(title), str(desc), metrics[metric], target, group)
             for key, icon, title, desc, metric, target, group in DEFINITIONS]
    groups = [{"key": key, "label": label, "items": [a for a in items if a.group == key]} for key, label in GROUPS]
    return {"groups": groups, "earned": sum(1 for a in items if a.earned), "total": len(items), "items": items}
