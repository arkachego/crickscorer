"""Match API routes — create, read, and lifecycle."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.match import ErrorResponse, MatchCreateRequest, MatchResponse
from app.services.matches import (
    create_match,
    get_match,
    list_matches,
    serialize_match,
    start_match,
    start_next_innings,
)

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get(
    "",
    response_model=list[MatchResponse],
    summary="List matches",
    description=(
        "Return persisted matches for discovery, newest first. "
        "Includes innings metadata when present; no delivery/scoring data."
    ),
)
def list_matches_endpoint(db: Session = Depends(get_db)) -> list[MatchResponse]:
    return [serialize_match(match, db) for match in list_matches(db)]


@router.get(
    "/{match_id}",
    response_model=MatchResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Match not found"},
        422: {"description": "Invalid match id"},
    },
    summary="Get a match",
    description="Return a single match with innings metadata.",
)
def get_match_endpoint(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> MatchResponse:
    return serialize_match(get_match(db, match_id), db)


@router.post(
    "",
    response_model=MatchResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Domain validation failure"},
        404: {"model": ErrorResponse, "description": "Referenced team not found"},
        422: {"description": "Request validation failure"},
    },
    summary="Create a match",
    description=(
        "Create a new cricket match between two distinct teams. "
        "Newly created matches always start with status CREATED. "
        "TEST format is rejected. "
        "T10/T20/ONE_DAY use fixed overs (10/20/50); CUSTOM requires explicit overs."
    ),
)
def create_match_endpoint(
    payload: MatchCreateRequest,
    db: Session = Depends(get_db),
) -> MatchResponse:
    return serialize_match(create_match(db, payload), db)


@router.post(
    "/{match_id}/start",
    response_model=MatchResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Match not found"},
        409: {"model": ErrorResponse, "description": "Invalid lifecycle transition"},
        422: {"description": "Invalid match id"},
    },
    summary="Start a match",
    description=(
        "Start a CREATED match: create innings 1 for the batting-first team, "
        "mark it IN_PROGRESS, and transition the match to IN_PROGRESS."
    ),
)
def start_match_endpoint(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> MatchResponse:
    return serialize_match(start_match(db, match_id), db)


@router.post(
    "/{match_id}/innings/start",
    response_model=MatchResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Match not found"},
        409: {"model": ErrorResponse, "description": "Invalid lifecycle transition"},
        422: {"description": "Invalid match id"},
    },
    summary="Start the next innings",
    description=(
        "From INNINGS_BREAK, create and start innings 2 with batting/bowling sides "
        "reversed, and transition the match to IN_PROGRESS."
    ),
)
def start_next_innings_endpoint(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> MatchResponse:
    return serialize_match(start_next_innings(db, match_id), db)
