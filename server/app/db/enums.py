"""Domain enumerations mapped to PostgreSQL ENUM types.

Player roles are relational (`roles` + `player_role` M2M), not an enum.
"""

from __future__ import annotations

from enum import StrEnum


class MatchFormat(StrEnum):
    T10 = "T10"
    T20 = "T20"
    ONE_DAY = "ONE_DAY"
    CUSTOM = "CUSTOM"
    TEST = "TEST"  # Schema supports TEST; app creation rejects until Test support exists.


class MatchStatus(StrEnum):
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    INNINGS_BREAK = "INNINGS_BREAK"
    COMPLETED = "COMPLETED"


class InningsStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class DismissalType(StrEnum):
    BOWLED = "BOWLED"
    CAUGHT = "CAUGHT"
    LBW = "LBW"
    STUMPED = "STUMPED"
    RUN_OUT = "RUN_OUT"
    HIT_WICKET = "HIT_WICKET"


class DeliveryType(StrEnum):
    """Mutually exclusive delivery outcomes for the scoring engine."""

    NORMAL = "NORMAL"
    WIDE = "WIDE"
    NO_BALL = "NO_BALL"
    BYE = "BYE"
    LEG_BYE = "LEG_BYE"
