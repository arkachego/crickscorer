"""Shared Phase 18 test factories — reduce per-file fixture duplication."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import MatchFormat
from app.db.models import BatterReplacement, Delivery, Innings, Match, Player, Team
from app.db.seed import seed_database
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match, start_match

SeededSides = tuple[Team, Team, Player, Player, Player]


@pytest.fixture()
def seeded_sides(db: Session) -> SeededSides:
    """India vs Pakistan with common striker / non-striker / bowler."""
    seed_database(db)
    india = db.scalar(select(Team).where(Team.short_code == "IND"))
    pakistan = db.scalar(select(Team).where(Team.short_code == "PAK"))
    assert india is not None and pakistan is not None

    def by_name(team_id: uuid.UUID, name: str) -> Player:
        player = db.scalar(
            select(Player)
            .where(Player.team_id == team_id, Player.name == name)
            .options(selectinload(Player.roles))
        )
        assert player is not None
        return player

    return (
        india,
        pakistan,
        by_name(india.id, "Abhishek Sharma"),
        by_name(india.id, "Shubman Gill"),
        by_name(pakistan.id, "Shaheen Afridi"),
    )


@pytest.fixture()
def started_match(
    db: Session, seeded_sides: SeededSides
) -> Generator[tuple[Match, Innings, SeededSides], None, None]:
    india, pakistan, *_ = seeded_sides
    match = create_match(
        db,
        MatchCreateRequest(
            team_1_id=india.id,
            team_2_id=pakistan.id,
            format=MatchFormat.T20,
            batting_first_team_id=india.id,
            overs=None,
        ),
    )
    match = start_match(db, match.id)
    innings = next(i for i in match.innings if i.innings_number == 1)
    yield match, innings, seeded_sides
    innings_ids = list(db.scalars(select(Innings.id).where(Innings.match_id == match.id)))
    if innings_ids:
        db.execute(
            delete(BatterReplacement).where(BatterReplacement.innings_id.in_(innings_ids))
        )
        db.execute(delete(Delivery).where(Delivery.innings_id.in_(innings_ids)))
        db.execute(delete(Innings).where(Innings.id.in_(innings_ids)))
    db.execute(delete(Match).where(Match.id == match.id))
    db.commit()
