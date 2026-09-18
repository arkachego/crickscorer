"""Team API routes (list teams + roster for Admin selectors)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.match import ErrorResponse
from app.schemas.team import PlayerResponse, TeamResponse
from app.services.teams import list_team_players, list_teams

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get(
    "",
    response_model=list[TeamResponse],
    summary="List teams",
    description="Return teams available for match creation selectors.",
)
def list_teams_endpoint(db: Session = Depends(get_db)) -> list[TeamResponse]:
    teams = list_teams(db)
    return [TeamResponse.model_validate(team) for team in teams]


@router.get(
    "/{team_id}/players",
    response_model=list[PlayerResponse],
    responses={
        404: {"model": ErrorResponse, "description": "Team not found"},
        422: {"description": "Invalid team id"},
    },
    summary="List team players",
    description=(
        "Return the team roster for Admin scoring selectors. "
        "Includes batting_order (null for coaches) and role names."
    ),
)
def list_team_players_endpoint(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[PlayerResponse]:
    return list_team_players(db, team_id)
