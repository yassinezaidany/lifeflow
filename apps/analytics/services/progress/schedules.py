"""Day classification: which days of a challenge are active, rest, paused or outside."""
from __future__ import annotations

from datetime import date
from enum import Enum


class DayType(str, Enum):
    ACTIVE = "active"      # the challenge expects something on this day
    REST = "rest"          # not scheduled, or explicitly marked as a rest day
    PAUSED = "paused"      # inside a pause period: excluded from evaluation
    OUTSIDE = "outside"    # before start / after end


def effective_end(challenge) -> date | None:
    """Last evaluated day: the end date, or the early closing date if any."""
    ends = [d for d in (challenge.end_date, challenge.closed_on) if d is not None]
    return min(ends) if ends else None


class ChallengeCalendar:
    def __init__(self, challenge, rest_days: set[date], today: date):
        self.challenge = challenge
        self.start = challenge.start_date
        self.end = effective_end(challenge)
        self.rest_days = rest_days
        cache = getattr(challenge, "_prefetched_objects_cache", {})
        pauses = list(cache["pauses"]) if "pauses" in cache else list(challenge.pauses.all())
        # An open pause runs until "today": the future is unknown.
        self.pauses = [(p.start_date, p.end_date or max(today, p.start_date)) for p in pauses]
        self._schedules = challenge._prefetched("schedules")

    def in_range(self, day: date) -> bool:
        return day >= self.start and (self.end is None or day <= self.end)

    def is_paused(self, day: date) -> bool:
        return any(s <= day <= e for s, e in self.pauses)

    def schedule_on(self, day: date):
        found = None
        for s in self._schedules:
            if s.effective_from <= day and (s.effective_to is None or day <= s.effective_to):
                found = s
        if found is None and self._schedules:
            # Days before the first version (e.g. start date moved back) use the first version.
            first = self._schedules[0]
            if day < first.effective_from:
                found = first
        return found

    def classify(self, day: date) -> DayType:
        if not self.in_range(day):
            return DayType.OUTSIDE
        if self.is_paused(day):
            return DayType.PAUSED
        schedule = self.schedule_on(day)
        if schedule is not None and not schedule.is_scheduled(day):
            return DayType.REST
        if day in self.rest_days:
            return DayType.REST
        return DayType.ACTIVE
