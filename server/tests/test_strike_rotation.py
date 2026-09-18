"""Unit tests for strike rotation helpers and delivery side-effects."""

from __future__ import annotations

import uuid

from app.services.strike_rotation import (
    crossing_runs_for_rotation,
    rotate_strike_ids,
)


def test_crossing_runs_normal_and_extras() -> None:
    assert (
        crossing_runs_for_rotation(
            bat_runs=1, wide_runs=0, bye_runs=0, leg_bye_runs=0
        )
        == 1
    )
    assert (
        crossing_runs_for_rotation(
            bat_runs=0, wide_runs=1, bye_runs=0, leg_bye_runs=0
        )
        == 0
    )
    assert (
        crossing_runs_for_rotation(
            bat_runs=0, wide_runs=3, bye_runs=0, leg_bye_runs=0
        )
        == 2
    )
    assert (
        crossing_runs_for_rotation(
            bat_runs=0, wide_runs=0, bye_runs=1, leg_bye_runs=0
        )
        == 1
    )
    assert (
        crossing_runs_for_rotation(
            bat_runs=1, wide_runs=0, bye_runs=0, leg_bye_runs=2
        )
        == 3
    )


def test_rotate_on_odd_runs_only() -> None:
    a = uuid.uuid4()
    b = uuid.uuid4()
    assert rotate_strike_ids(a, b, crossing_runs=1, ended_over=False) == (b, a)
    assert rotate_strike_ids(a, b, crossing_runs=2, ended_over=False) == (a, b)
    assert rotate_strike_ids(a, b, crossing_runs=0, ended_over=False) == (a, b)


def test_rotate_end_of_over_and_double_swap() -> None:
    a = uuid.uuid4()
    b = uuid.uuid4()
    # Even runs + end of over → one swap.
    assert rotate_strike_ids(a, b, crossing_runs=0, ended_over=True) == (b, a)
    # Odd runs + end of over → two swaps → net unchanged.
    assert rotate_strike_ids(a, b, crossing_runs=1, ended_over=True) == (a, b)
