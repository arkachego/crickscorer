"""Innings lifecycle, delivery submission, and batter replacement API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.delivery import (
    DeliveryCreateRequest,
    DeliveryHistoryItem,
    DeliveryResponse,
    ReplacementRequest,
)
from app.schemas.match import ErrorResponse, MatchResponse, UndoResponse
from app.services.matches import complete_innings, serialize_match
from app.services.reconstruction import undo_latest_delivery
from app.services.scoring import list_innings_deliveries, submit_delivery, submit_replacement

router = APIRouter(prefix="/innings", tags=["innings"])


@router.post(
    "/{innings_id}/complete",
    response_model=MatchResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Innings or match not found"},
        409: {"model": ErrorResponse, "description": "Invalid lifecycle transition"},
        422: {"description": "Invalid innings id"},
    },
    summary="Complete an innings",
    description=(
        "Complete an IN_PROGRESS innings. The match becomes INNINGS_BREAK after "
        "innings 1, or COMPLETED after innings 2."
    ),
)
def complete_innings_endpoint(
    innings_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> MatchResponse:
    return serialize_match(complete_innings(db, innings_id), db)


@router.get(
    "/{innings_id}/deliveries",
    response_model=list[DeliveryHistoryItem],
    responses={
        404: {"model": ErrorResponse, "description": "Innings not found"},
        422: {"description": "Invalid innings id"},
    },
    summary="List innings deliveries",
    description=(
        "Return chronological delivery history for Admin scoring recent-history. "
        "Read-only; does not mutate scoring state."
    ),
)
def list_deliveries_endpoint(
    innings_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[DeliveryHistoryItem]:
    return list_innings_deliveries(db, innings_id)


@router.post(
    "/{innings_id}/deliveries",
    response_model=DeliveryResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid participants or outcome"},
        404: {"model": ErrorResponse, "description": "Innings or player not found"},
        409: {"model": ErrorResponse, "description": "Invalid match/innings/Free Hit state"},
        422: {"description": "Request validation failed"},
    },
    summary="Submit one delivery",
    description=(
        "Submit exactly one delivery for an IN_PROGRESS innings. "
        "Supports NORMAL, WIDE, NO_BALL, BYE, LEG_BYE and optional wickets. "
        "Free Hit prohibits wickets. Replacement must be selected via "
        "POST /replacement before the next delivery after a non-terminal wicket."
    ),
)
def submit_delivery_endpoint(
    innings_id: uuid.UUID,
    payload: DeliveryCreateRequest,
    db: Session = Depends(get_db),
) -> DeliveryResponse:
    return submit_delivery(db, innings_id, payload)


@router.post(
    "/{innings_id}/replacement",
    response_model=MatchResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid replacement player"},
        404: {"model": ErrorResponse, "description": "Innings or player not found"},
        409: {"model": ErrorResponse, "description": "Replacement not required / invalid state"},
        422: {"description": "Request validation failed"},
    },
    summary="Select replacement batter",
    description=(
        "Fill the vacant active-batter slot after a wicket. "
        "Required before the next delivery when replacement_required is true."
    ),
)
def submit_replacement_endpoint(
    innings_id: uuid.UUID,
    payload: ReplacementRequest,
    db: Session = Depends(get_db),
) -> MatchResponse:
    return submit_replacement(db, innings_id, payload)


@router.post(
    "/{innings_id}/undo",
    response_model=UndoResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Innings or match not found"},
        409: {"model": ErrorResponse, "description": "Nothing to undo / invalid state"},
        422: {"description": "Invalid innings id"},
    },
    summary="Undo latest delivery",
    description=(
        "Remove the highest-sequence delivery for the innings and reconstruct "
        "active batters, Free Hit, replacement-required, and lifecycle state "
        "from remaining delivery and replacement history."
    ),
)
def undo_delivery_endpoint(
    innings_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> UndoResponse:
    return undo_latest_delivery(db, innings_id)
