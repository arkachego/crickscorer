"""Pydantic schemas for delivery submission (scoring + extras + wickets)."""

from __future__ import annotations

import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.enums import DeliveryType, DismissalType, InningsStatus, MatchStatus

VALID_BAT_RUNS = frozenset({0, 1, 2, 3, 4, 6})

# Phase 11 supports these five; HIT_WICKET exists in DB enum but is rejected.
PHASE_11_DISMISSAL_TYPES = frozenset(
    {
        DismissalType.BOWLED,
        DismissalType.CAUGHT,
        DismissalType.LBW,
        DismissalType.RUN_OUT,
        DismissalType.STUMPED,
    }
)


class WicketRequest(BaseModel):
    """Optional wicket payload attached to a delivery."""

    model_config = ConfigDict(extra="forbid")

    dismissed_player_id: uuid.UUID
    dismissal_type: DismissalType


class DeliveryCreateRequest(BaseModel):
    """Client-supplied fields for one delivery. Server derives position and totals.

    Mutually exclusive ``delivery_type`` values:

    - NORMAL / NO_BALL → ``bat_runs`` ∈ {0,1,2,3,4,6}; no ``extra_runs``
    - WIDE / BYE / LEG_BYE → ``extra_runs`` ≥ 1; ``bat_runs`` must be 0

    Optional ``wicket`` is validated against delivery type and Free Hit by the service.
    """

    model_config = ConfigDict(extra="forbid")

    striker_id: uuid.UUID
    non_striker_id: uuid.UUID
    bowler_id: uuid.UUID
    delivery_type: DeliveryType = DeliveryType.NORMAL
    bat_runs: int = Field(
        default=0,
        description="Bat runs for NORMAL/NO_BALL. Must be 0 for WIDE/BYE/LEG_BYE.",
    )
    extra_runs: int | None = Field(
        default=None,
        description="Extra amount for WIDE/BYE/LEG_BYE (≥ 1). Forbidden for NORMAL/NO_BALL.",
    )
    wicket: WicketRequest | None = None

    @model_validator(mode="after")
    def validate_outcome_combination(self) -> Self:
        dtype = self.delivery_type
        if dtype in {DeliveryType.NORMAL, DeliveryType.NO_BALL}:
            if self.extra_runs is not None:
                raise ValueError(
                    f"extra_runs is not allowed for {dtype.value} deliveries."
                )
            if self.bat_runs not in VALID_BAT_RUNS:
                raise ValueError("bat_runs must be one of 0, 1, 2, 3, 4, or 6.")
            return self

        # WIDE / BYE / LEG_BYE
        if self.bat_runs != 0:
            raise ValueError(f"bat_runs must be 0 for {dtype.value} deliveries.")
        if self.extra_runs is None:
            raise ValueError(f"extra_runs is required for {dtype.value} deliveries.")
        if self.extra_runs < 1:
            raise ValueError(f"extra_runs must be >= 1 for {dtype.value} deliveries.")
        return self


class PlayerBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class WicketInfo(BaseModel):
    dismissed_player: PlayerBrief
    dismissal_type: DismissalType


class DeliveryResponse(BaseModel):
    """Authoritative delivery result after persistence."""

    id: uuid.UUID
    innings_id: uuid.UUID
    sequence_no: int
    over_number: int = Field(
        description="Zero-based over index (first over is 0). Human over = over_number + 1.",
    )
    ball_in_over: int
    striker: PlayerBrief
    non_striker: PlayerBrief
    bowler: PlayerBrief
    delivery_type: DeliveryType
    bat_runs: int
    wide_runs: int
    no_ball_runs: int
    bye_runs: int
    leg_bye_runs: int
    total_runs: int
    is_legal: bool
    is_free_hit: bool
    wicket: WicketInfo | None = None
    innings_status: InningsStatus
    match_status: MatchStatus
    innings_total_runs: int
    replacement_required: bool = False


class ReplacementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: uuid.UUID


class DeliveryHistoryItem(BaseModel):
    """Compact delivery row for Admin recent-history display."""

    id: uuid.UUID
    sequence_no: int
    over_number: int
    ball_in_over: int
    delivery_type: DeliveryType
    bat_runs: int
    wide_runs: int
    no_ball_runs: int
    bye_runs: int
    leg_bye_runs: int
    total_runs: int
    is_legal: bool
    is_free_hit: bool
    striker: PlayerBrief
    non_striker: PlayerBrief
    bowler: PlayerBrief
    wicket: WicketInfo | None = None
