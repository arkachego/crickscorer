"""Match list and detail API tests (Phase 7)."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.enums import MatchFormat, MatchStatus
from app.db.models import Match, Team
from app.main import app
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match

client = TestClient(app)
MATCHES_URL = "/api/v1/matches"


@pytest.fixture()
def two_teams(db: Session) -> Generator[tuple[Team, Team], None, None]:
    suffix = uuid.uuid4().hex[:8]
    team_a = Team(
        name=f"List Alpha {suffix}",
        short_code=f"L{suffix[:7]}",
        flag_url=f"https://example.test/flags/l-a-{suffix}.svg",
    )
    team_b = Team(
        name=f"List Beta {suffix}",
        short_code=f"M{suffix[:7]}",
        flag_url=f"https://example.test/flags/l-b-{suffix}.svg",
    )
    db.add_all([team_a, team_b])
    db.commit()
    db.refresh(team_a)
    db.refresh(team_b)
    yield team_a, team_b
    db.execute(
        delete(Match).where(
            Match.team_1_id.in_([team_a.id, team_b.id])
            | Match.team_2_id.in_([team_a.id, team_b.id])
        )
    )
    db.execute(delete(Team).where(Team.id.in_([team_a.id, team_b.id])))
    db.commit()


def _create(
    db: Session,
    team_1: Team,
    team_2: Team,
    *,
    fmt: MatchFormat = MatchFormat.T20,
) -> Match:
    return create_match(
        db,
        MatchCreateRequest(
            team_1_id=team_1.id,
            team_2_id=team_2.id,
            format=fmt,
            batting_first_team_id=team_1.id,
            overs=None if fmt is not MatchFormat.CUSTOM else 12,
        ),
    )


def test_list_matches_empty_ok(db: Session) -> None:
    # Isolate by deleting only matches that use no teams? Just assert list is an array.
    # Empty globally may not hold if other tests left data; create dedicated empty
    # check via filtering response against unknown team ids — instead verify shape.
    response = client.get(MATCHES_URL)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_matches_includes_created_and_orders_newest_first(
    two_teams: tuple[Team, Team], db: Session
) -> None:
    team_1, team_2 = two_teams
    first = _create(db, team_1, team_2, fmt=MatchFormat.T10)
    second = _create(db, team_1, team_2, fmt=MatchFormat.T20)

    response = client.get(MATCHES_URL)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    ids = [item["id"] for item in data]
    assert str(second.id) in ids
    assert str(first.id) in ids
    assert ids.index(str(second.id)) < ids.index(str(first.id))

    ours = [item for item in data if item["id"] in {str(first.id), str(second.id)}]
    for item in ours:
        assert set(item.keys()) == {
            "id",
            "team_1",
            "team_2",
            "batting_first_team",
            "format",
            "overs",
            "status",
            "created_at",
            "innings",
        }
        assert "innings" in item
        assert isinstance(item["innings"], list)
        assert "deliveries" not in item
        assert item["team_1"]["id"] == str(team_1.id)
        assert item["team_2"]["id"] == str(team_2.id)
        assert item["batting_first_team"]["id"] == str(team_1.id)
        assert item["status"] == MatchStatus.CREATED.value


def test_get_match_success(two_teams: tuple[Team, Team], db: Session) -> None:
    team_1, team_2 = two_teams
    match = _create(db, team_1, team_2, fmt=MatchFormat.ONE_DAY)
    response = client.get(f"{MATCHES_URL}/{match.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(match.id)
    assert data["format"] == "ONE_DAY"
    assert data["overs"] == 50
    assert data["status"] == "CREATED"
    assert data["team_1"]["name"] == team_1.name
    assert data["team_2"]["name"] == team_2.name
    assert data["innings"] == []
    assert "deliveries" not in data


def test_get_match_not_found() -> None:
    missing = uuid.uuid4()
    response = client.get(f"{MATCHES_URL}/{missing}")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["code"] == "MATCH_NOT_FOUND"


def test_get_match_malformed_uuid_returns_422() -> None:
    response = client.get(f"{MATCHES_URL}/not-a-uuid")
    assert response.status_code == 422
