"""Shared ball-position and strike-rotation helpers.

Kept free of ORM/service imports so scoring and reconstruction can both use them
without circular dependencies.
"""

from __future__ import annotations

import uuid

LEGAL_BALLS_PER_OVER = 6


def max_legal_deliveries(overs: int) -> int:
    """Configured overs × six legal balls per over."""
    return overs * LEGAL_BALLS_PER_OVER


def next_delivery_position(
    *,
    delivery_count: int,
    legal_count: int,
) -> tuple[int, int, int]:
    """Derive (sequence_no, over_number, ball_in_over)."""
    sequence_no = delivery_count + 1
    over_number = legal_count // LEGAL_BALLS_PER_OVER
    ball_in_over = (legal_count % LEGAL_BALLS_PER_OVER) + 1
    return sequence_no, over_number, ball_in_over


def crossing_runs_for_rotation(
    *,
    bat_runs: int,
    wide_runs: int,
    bye_runs: int,
    leg_bye_runs: int,
) -> int:
    """Runs that move batters between ends (excludes automatic wide/no-ball penalties)."""
    runnable = int(bat_runs) + int(bye_runs) + int(leg_bye_runs)
    if int(wide_runs) > 0:
        # Wide penalty itself does not cross; additional runs taken do.
        runnable += max(0, int(wide_runs))
    return runnable


def rotate_strike_ids(
    striker_id: uuid.UUID | None,
    non_striker_id: uuid.UUID | None,
    *,
    crossing_runs: int,
    ended_over: bool,
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Return the active pair for the next ball after odd-run / end-of-over swaps."""
    if striker_id is None or non_striker_id is None:
        return striker_id, non_striker_id
    swaps = 0
    if crossing_runs % 2 == 1:
        swaps += 1
    if ended_over:
        swaps += 1
    if swaps % 2 == 1:
        return non_striker_id, striker_id
    return striker_id, non_striker_id
