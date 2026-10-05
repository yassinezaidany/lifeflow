"""Progress status rules (documented in docs/07-PROGRESS-ENGINE.md)."""
from __future__ import annotations

from enum import Enum

AHEAD_RATIO = 1.10   # actual >= 110% of expected
BEHIND_RATIO = 0.90  # actual < 90% of expected


class ProgressStatus(str, Enum):
    NOT_STARTED = "not_started"
    ON_TRACK = "on_track"
    AHEAD = "ahead"
    BEHIND = "behind"
    COMPLETED = "completed"
    MISSED = "missed"
    PAUSED = "paused"
    REST_DAY = "rest_day"


def compute_status(
    *,
    not_started: bool,
    paused: bool,
    manually_completed: bool,
    ended: bool,
    actual: float,
    goal: float,
    expected: float | None,
    goal_is_final: bool,
    limit: bool = False,
) -> ProgressStatus:
    """
    Order of precedence:
      1. NOT_STARTED  – the evaluation date is before the start date
      2. COMPLETED    – marked completed, or the (final) goal is reached
      3. PAUSED       – challenge currently paused
      4. MISSED       – evaluation window is over and the goal was not reached
      5. AHEAD / ON_TRACK / BEHIND – actual compared with expected
    """
    if not_started:
        return ProgressStatus.NOT_STARTED
    if limit:
        return _limit_status(paused, manually_completed, ended, actual, goal, expected)
    if manually_completed or (goal_is_final and goal > 0 and actual >= goal - 1e-9):
        return ProgressStatus.COMPLETED
    if paused:
        return ProgressStatus.PAUSED
    if ended:
        return ProgressStatus.COMPLETED if goal > 0 and actual >= goal - 1e-9 else ProgressStatus.MISSED
    if expected is None:
        return ProgressStatus.ON_TRACK
    if expected <= 1e-9:
        return ProgressStatus.AHEAD if actual > 1e-9 else ProgressStatus.ON_TRACK
    ratio = actual / expected
    if ratio >= AHEAD_RATIO:
        return ProgressStatus.AHEAD
    if ratio >= BEHIND_RATIO:
        return ProgressStatus.ON_TRACK
    return ProgressStatus.BEHIND


def _limit_status(paused, manually_completed, ended, actual, goal, expected) -> ProgressStatus:
    """Limit goals ("at most"): being under the consumed budget is good."""
    if manually_completed:
        return ProgressStatus.COMPLETED
    if paused:
        return ProgressStatus.PAUSED
    if ended:
        return ProgressStatus.COMPLETED if actual <= goal + 1e-9 else ProgressStatus.MISSED
    if expected is None:
        return ProgressStatus.ON_TRACK
    if expected <= 1e-9:
        return ProgressStatus.BEHIND if actual > 1e-9 else ProgressStatus.ON_TRACK
    ratio = actual / expected
    if ratio <= 2 - AHEAD_RATIO:      # ≤ 90 % of the budget used so far
        return ProgressStatus.AHEAD
    if ratio <= 2 - BEHIND_RATIO:     # ≤ 110 %
        return ProgressStatus.ON_TRACK
    return ProgressStatus.BEHIND