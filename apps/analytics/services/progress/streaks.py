"""Streak computation over evaluation units (days, weeks or months).

Units with no target (rest days, paused periods) are removed *before* calling these
functions, so they neither break nor extend a streak.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StreakUnit:
    achieved: bool
    due: bool  # fully elapsed (a unit still in progress cannot break a streak)


def current_streak(units: list[StreakUnit]) -> int:
    streak = 0
    for i, unit in enumerate(reversed(units)):
        if unit.achieved:
            streak += 1
        elif i == 0 and not unit.due:
            continue  # today / this week is not over yet: keep the streak alive
        else:
            break
    return streak


def best_streak(units: list[StreakUnit]) -> int:
    best = run = 0
    for unit in units:
        if unit.achieved:
            run += 1
            best = max(best, run)
        elif unit.due:
            run = 0
    return best
