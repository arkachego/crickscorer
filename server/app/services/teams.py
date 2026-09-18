"""Team and player read services."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Player, Team
from app.exceptions import NotFoundError
from app.schemas.team import PlayerResponse


def list_teams(session: Session) -> list[Team]:
    """Return all teams ordered by name for Admin selectors."""
    return list(session.scalars(select(Team).order_by(Team.name)))


def get_team(session: Session, team_id: uuid.UUID) -> Team:
    team = session.scalar(select(Team).where(Team.id == team_id))
    if team is None:
        raise NotFoundError("TEAM_NOT_FOUND", "Team was not found.")
    return team


def list_team_players(session: Session, team_id: uuid.UUID) -> list[PlayerResponse]:
    """Return roster for a team (playing XI + coach), ordered for selectors."""
    get_team(session, team_id)
    players = list(
        session.scalars(
            select(Player)
            .where(Player.team_id == team_id)
            .options(selectinload(Player.roles))
            .order_by(Player.batting_order.asc().nulls_last(), Player.name.asc())
        )
    )
    return [
        PlayerResponse(
            id=player.id,
            team_id=player.team_id,
            name=player.name,
            batting_order=player.batting_order,
            roles=sorted(role.name for role in player.roles),
        )
        for player in players
    ]
