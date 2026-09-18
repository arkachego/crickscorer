"""Pydantic schemas for match creation and lifecycle reads."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import InningsStatus, MatchFormat, MatchStatus
from app.schemas.delivery import PlayerBrief


class TeamSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    short_code: str
    flag_url: str


class BatterScorecardRow(BaseModel):
    player: PlayerBrief
    dismissal_text: str
    is_not_out: bool
    runs: int
    balls: int
    fours: int
    sixes: int
    strike_rate: float


class BowlerScorecardRow(BaseModel):
    player: PlayerBrief
    overs: str
    maidens: int
    runs: int
    wickets: int
    noballs: int
    wides: int
    economy: float


class ExtrasBreakdown(BaseModel):
    byes: int = 0
    leg_byes: int = 0
    wides: int = 0
    noballs: int = 0
    total: int = 0


class InningsScorecard(BaseModel):
    """Per-innings batting and bowling figures derived from deliveries."""

    batters: list[BatterScorecardRow] = Field(default_factory=list)
    extras: ExtrasBreakdown = Field(default_factory=ExtrasBreakdown)
    did_not_bat: list[PlayerBrief] = Field(default_factory=list)
    bowlers: list[BowlerScorecardRow] = Field(default_factory=list)
    total_runs: int = 0
    wickets: int = 0
    overs_display: str = "0.0"
    run_rate: float = 0.0


class InningsResponse(BaseModel):
    """Innings metadata including active-batter / replacement / scoring snapshot."""

    id: uuid.UUID
    innings_number: int
    batting_team: TeamSummary
    bowling_team: TeamSummary
    status: InningsStatus
    created_at: datetime
    striker: PlayerBrief | None = None
    non_striker: PlayerBrief | None = None
    replacement_required: bool = False
    target: int | None = None
    # Authoritative scoring snapshot (reconstructed from delivery history).
    innings_total_runs: int = 0
    legal_delivery_count: int = 0
    delivery_count: int = 0
    next_over_number: int = 0
    next_ball_in_over: int = 1
    free_hit_pending: bool = False
    wickets: int = 0
    dismissed_player_ids: list[uuid.UUID] = Field(default_factory=list)
    scorecard: InningsScorecard = Field(default_factory=InningsScorecard)


class MatchCreateRequest(BaseModel):
    """Client-supplied fields for creating a match. Server controls id/status."""

    model_config = ConfigDict(extra="forbid")

    team_1_id: uuid.UUID
    team_2_id: uuid.UUID
    format: MatchFormat
    batting_first_team_id: uuid.UUID
    overs: int | None = Field(
        default=None,
        description=(
            "Required for CUSTOM. For T10/T20/ONE_DAY may be omitted "
            "(defaults to 10/20/50) or must match the fixed value."
        ),
    )


class MatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    team_1: TeamSummary
    team_2: TeamSummary
    batting_first_team: TeamSummary
    format: MatchFormat
    overs: int
    status: MatchStatus
    created_at: datetime
    innings: list[InningsResponse] = Field(default_factory=list)


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class UndoResponse(BaseModel):
    """Authoritative match/innings projection after undoing the latest delivery."""

    match: MatchResponse
    innings_id: uuid.UUID
    delivery_count: int
    legal_delivery_count: int
    innings_total_runs: int
    next_over_number: int
    next_ball_in_over: int
    free_hit_pending: bool
    replacement_required: bool
    innings_status: InningsStatus
    match_status: MatchStatus
    striker: PlayerBrief | None = None
    non_striker: PlayerBrief | None = None
