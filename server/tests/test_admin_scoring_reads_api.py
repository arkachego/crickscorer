"""Minimal read endpoints for Admin scoring UI (Phase 13)."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import MatchFormat
from app.db.models import Delivery, Innings, Match, Player, Team
from app.db.seed import seed_database
from app.main import app
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match, start_match

client = TestClient(app)


@pytest.fixture()
def seeded(db: Session) -> tuple[Team, Team, Player, Player, Player]:
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
def started(
    db: Session, seeded: tuple[Team, Team, Player, Player, Player]
) -> Generator[tuple[Match, Innings, tuple[Team, Team, Player, Player, Player]], None, None]:
    india, pakistan, *_ = seeded
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
    yield match, innings, seeded
    innings_ids = list(db.scalars(select(Innings.id).where(Innings.match_id == match.id)))
    if innings_ids:
        db.execute(delete(Delivery).where(Delivery.innings_id.in_(innings_ids)))
        db.execute(delete(Innings).where(Innings.id.in_(innings_ids)))
    db.execute(delete(Match).where(Match.id == match.id))
    db.commit()


def test_list_team_players_includes_roles_and_coach(
    db: Session, seeded: tuple[Team, Team, Player, Player, Player]
) -> None:
    india, *_ = seeded
    response = client.get(f"/api/v1/teams/{india.id}/players")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 12
    names = {row["name"] for row in data}
    assert "Gautam Gambhir" in names
    coach = next(row for row in data if row["name"] == "Gautam Gambhir")
    assert coach["batting_order"] is None
    assert "Coach" in coach["roles"]
    bumrah = next(row for row in data if row["name"] == "Jasprit Bumrah")
    assert bumrah["batting_order"] == 10
    assert "Bowler" in bumrah["roles"]


def test_list_team_players_404(db: Session) -> None:
    response = client.get(
        f"/api/v1/teams/{uuid.uuid4()}/players"
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TEAM_NOT_FOUND"


def test_match_get_includes_scoring_snapshot(
    db: Session,
    started: tuple[Match, Innings, tuple[Team, Team, Player, Player, Player]],
) -> None:
    match, innings, sides = started
    _, _, striker, non_striker, bowler = sides
    post = client.post(
        f"/api/v1/innings/{innings.id}/deliveries",
        json={
            "striker_id": str(striker.id),
            "non_striker_id": str(non_striker.id),
            "bowler_id": str(bowler.id),
            "delivery_type": "NORMAL",
            "bat_runs": 4,
        },
    )
    assert post.status_code == 200

    response = client.get(f"/api/v1/matches/{match.id}")
    assert response.status_code == 200
    payload = response.json()
    inn = next(i for i in payload["innings"] if i["id"] == str(innings.id))
    assert inn["innings_total_runs"] == 4
    assert inn["legal_delivery_count"] == 1
    assert inn["delivery_count"] == 1
    assert inn["wickets"] == 0
    assert inn["free_hit_pending"] is False
    assert inn["next_over_number"] == 0
    assert inn["next_ball_in_over"] == 2


def test_list_deliveries_chronological(
    db: Session,
    started: tuple[Match, Innings, tuple[Team, Team, Player, Player, Player]],
) -> None:
    _, innings, sides = started
    _, _, striker, non_striker, bowler = sides
    base = {
        "striker_id": str(striker.id),
        "non_striker_id": str(non_striker.id),
        "bowler_id": str(bowler.id),
    }
    assert (
        client.post(
            f"/api/v1/innings/{innings.id}/deliveries",
            json={**base, "delivery_type": "NORMAL", "bat_runs": 1},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/innings/{innings.id}/deliveries",
            json={**base, "delivery_type": "WIDE", "bat_runs": 0, "extra_runs": 1},
        ).status_code
        == 200
    )

    response = client.get(f"/api/v1/innings/{innings.id}/deliveries")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["sequence_no"] == 1
    assert data[0]["delivery_type"] == "NORMAL"
    assert data[0]["total_runs"] == 1
    assert data[1]["sequence_no"] == 2
    assert data[1]["delivery_type"] == "WIDE"
    assert data[1]["is_legal"] is False


def test_list_deliveries_404(db: Session) -> None:
    response = client.get(f"/api/v1/innings/{uuid.uuid4()}/deliveries")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "INNINGS_NOT_FOUND"
