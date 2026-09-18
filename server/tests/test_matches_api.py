"""Match creation API tests (Phase 5)."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.db.enums import MatchFormat, MatchStatus
from app.db.models import Match, Team
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)
MATCHES_URL = "/api/v1/matches"


@pytest.fixture()
def two_teams(db: Session) -> Generator[tuple[Team, Team], None, None]:
    suffix = uuid.uuid4().hex[:8]
    team_a = Team(
        name=f"Team Alpha {suffix}",
        short_code=f"A{suffix[:7]}",
        flag_url=f"https://example.test/flags/a-{suffix}.svg",
    )
    team_b = Team(
        name=f"Team Beta {suffix}",
        short_code=f"B{suffix[:7]}",
        flag_url=f"https://example.test/flags/b-{suffix}.svg",
    )
    db.add_all([team_a, team_b])
    db.commit()
    db.refresh(team_a)
    db.refresh(team_b)
    yield team_a, team_b
    _cleanup_teams(db, team_a.id, team_b.id)


@pytest.fixture()
def three_teams(db: Session) -> Generator[tuple[Team, Team, Team], None, None]:
    suffix = uuid.uuid4().hex[:8]
    teams = [
        Team(
            name=f"Team {label} {suffix}",
            short_code=f"{label[0]}{suffix[:7]}",
            flag_url=f"https://example.test/flags/{label.lower()}-{suffix}.svg",
        )
        for label in ("Alpha", "Beta", "Gamma")
    ]
    db.add_all(teams)
    db.commit()
    for team in teams:
        db.refresh(team)
    yield teams[0], teams[1], teams[2]
    _cleanup_teams(db, *(t.id for t in teams))


def _cleanup_teams(db: Session, *team_ids: uuid.UUID) -> None:
    db.execute(
        delete(Match).where(
            Match.team_1_id.in_(team_ids)
            | Match.team_2_id.in_(team_ids)
            | Match.batting_first_team_id.in_(team_ids)
        )
    )
    db.execute(delete(Team).where(Team.id.in_(team_ids)))
    db.commit()


def _payload(
    team_1: Team,
    team_2: Team,
    *,
    batting_first: Team | None = None,
    fmt: str = "T20",
    overs: int | None = None,
    extra: dict | None = None,
) -> dict:
    body: dict = {
        "team_1_id": str(team_1.id),
        "team_2_id": str(team_2.id),
        "format": fmt,
        "batting_first_team_id": str((batting_first or team_1).id),
    }
    if overs is not None:
        body["overs"] = overs
    if extra:
        body.update(extra)
    return body


def _assert_error(response, *, status_code: int, code: str | None = None) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert "detail" in body
    if status_code in {400, 404}:
        assert isinstance(body["detail"], dict)
        assert "code" in body["detail"]
        assert "message" in body["detail"]
        if code is not None:
            assert body["detail"]["code"] == code
    return body


def test_create_t20_match_success(two_teams: tuple[Team, Team], db: Session) -> None:
    team_1, team_2 = two_teams
    response = client.post(MATCHES_URL, json=_payload(team_1, team_2, fmt="T20"))
    assert response.status_code == 201
    data = response.json()

    assert data["status"] == MatchStatus.CREATED.value
    assert data["format"] == MatchFormat.T20.value
    assert data["overs"] == 20
    assert data["team_1"]["id"] == str(team_1.id)
    assert data["team_1"]["name"] == team_1.name
    assert data["team_1"]["short_code"] == team_1.short_code
    assert data["team_1"]["flag_url"] == team_1.flag_url
    assert data["team_2"]["id"] == str(team_2.id)
    assert data["batting_first_team"]["id"] == str(team_1.id)
    assert "created_at" in data

    match_id = uuid.UUID(data["id"])
    persisted = db.get(Match, match_id)
    assert persisted is not None
    assert persisted.status is MatchStatus.CREATED
    assert persisted.team_1_id == team_1.id
    assert persisted.team_2_id == team_2.id
    assert persisted.batting_first_team_id == team_1.id
    assert persisted.format is MatchFormat.T20
    assert persisted.overs == 20


def test_created_match_id_is_database_uuidv7(
    two_teams: tuple[Team, Team], db: Session
) -> None:
    team_1, team_2 = two_teams
    response = client.post(MATCHES_URL, json=_payload(team_1, team_2))
    assert response.status_code == 201
    match_id = uuid.UUID(response.json()["id"])
    assert match_id.version == 7

    row = db.execute(
        text(
            """
            SELECT id, uuid_extract_version(id) AS ver
            FROM matches
            WHERE id = :id
            """
        ),
        {"id": match_id},
    ).mappings().one()
    assert row["ver"] == 7
    assert row["id"] == match_id


@pytest.mark.parametrize(
    ("fmt", "overs", "expected_overs"),
    [
        ("T10", None, 10),
        ("T20", None, 20),
        ("ONE_DAY", None, 50),
        ("CUSTOM", 15, 15),
        ("T10", 10, 10),
        ("T20", 20, 20),
        ("ONE_DAY", 50, 50),
    ],
)
def test_supported_formats_accepted(
    two_teams: tuple[Team, Team],
    fmt: str,
    overs: int | None,
    expected_overs: int,
) -> None:
    team_1, team_2 = two_teams
    response = client.post(
        MATCHES_URL,
        json=_payload(team_1, team_2, fmt=fmt, overs=overs),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["format"] == fmt
    assert data["overs"] == expected_overs
    assert data["status"] == "CREATED"


def test_test_format_rejected(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    response = client.post(MATCHES_URL, json=_payload(team_1, team_2, fmt="TEST"))
    _assert_error(response, status_code=400, code="TEST_FORMAT_NOT_SUPPORTED")


def test_unknown_team_1_returns_404(two_teams: tuple[Team, Team]) -> None:
    _, team_2 = two_teams
    missing = uuid.uuid4()
    body = {
        "team_1_id": str(missing),
        "team_2_id": str(team_2.id),
        "format": "T20",
        "batting_first_team_id": str(team_2.id),
    }
    response = client.post(MATCHES_URL, json=body)
    _assert_error(response, status_code=404, code="TEAM_NOT_FOUND")


def test_unknown_team_2_returns_404(two_teams: tuple[Team, Team]) -> None:
    team_1, _ = two_teams
    missing = uuid.uuid4()
    body = {
        "team_1_id": str(team_1.id),
        "team_2_id": str(missing),
        "format": "T20",
        "batting_first_team_id": str(team_1.id),
    }
    response = client.post(MATCHES_URL, json=body)
    _assert_error(response, status_code=404, code="TEAM_NOT_FOUND")


def test_same_team_twice_rejected(two_teams: tuple[Team, Team]) -> None:
    team_1, _ = two_teams
    response = client.post(MATCHES_URL, json=_payload(team_1, team_1))
    _assert_error(response, status_code=400, code="TEAMS_MUST_BE_DISTINCT")


def test_batting_first_not_in_match_rejected(
    three_teams: tuple[Team, Team, Team],
) -> None:
    team_1, team_2, outsider = three_teams
    response = client.post(
        MATCHES_URL,
        json=_payload(team_1, team_2, batting_first=outsider),
    )
    _assert_error(response, status_code=400, code="BATTING_FIRST_NOT_IN_MATCH")


def test_unknown_batting_first_returns_404(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    body = {
        "team_1_id": str(team_1.id),
        "team_2_id": str(team_2.id),
        "format": "T20",
        "batting_first_team_id": str(uuid.uuid4()),
    }
    response = client.post(MATCHES_URL, json=body)
    _assert_error(response, status_code=404, code="TEAM_NOT_FOUND")


def test_custom_overs_required(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    response = client.post(MATCHES_URL, json=_payload(team_1, team_2, fmt="CUSTOM"))
    _assert_error(response, status_code=400, code="CUSTOM_OVERS_REQUIRED")


def test_custom_overs_must_be_positive(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    response = client.post(
        MATCHES_URL,
        json=_payload(team_1, team_2, fmt="CUSTOM", overs=0),
    )
    _assert_error(response, status_code=400, code="INVALID_OVERS")


def test_fixed_format_wrong_overs_rejected(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    response = client.post(
        MATCHES_URL,
        json=_payload(team_1, team_2, fmt="T20", overs=19),
    )
    _assert_error(response, status_code=400, code="INVALID_FIXED_FORMAT_OVERS")


def test_missing_team_1_id_returns_422(two_teams: tuple[Team, Team]) -> None:
    _, team_2 = two_teams
    body = {
        "team_2_id": str(team_2.id),
        "format": "T20",
        "batting_first_team_id": str(team_2.id),
    }
    response = client.post(MATCHES_URL, json=body)
    assert response.status_code == 422


def test_malformed_uuid_returns_422(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    body = _payload(team_1, team_2)
    body["team_1_id"] = "not-a-uuid"
    response = client.post(MATCHES_URL, json=body)
    assert response.status_code == 422


def test_missing_format_returns_422(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    body = {
        "team_1_id": str(team_1.id),
        "team_2_id": str(team_2.id),
        "batting_first_team_id": str(team_1.id),
    }
    response = client.post(MATCHES_URL, json=body)
    assert response.status_code == 422


def test_invalid_format_value_returns_422(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    response = client.post(
        MATCHES_URL,
        json=_payload(team_1, team_2, fmt="HUNDRED"),
    )
    assert response.status_code == 422


def test_missing_batting_first_returns_422(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    body = {
        "team_1_id": str(team_1.id),
        "team_2_id": str(team_2.id),
        "format": "T20",
    }
    response = client.post(MATCHES_URL, json=body)
    assert response.status_code == 422


def test_client_cannot_supply_id(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    response = client.post(
        MATCHES_URL,
        json=_payload(team_1, team_2, extra={"id": str(uuid.uuid4())}),
    )
    assert response.status_code == 422


def test_client_cannot_supply_status(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    response = client.post(
        MATCHES_URL,
        json=_payload(team_1, team_2, extra={"status": "IN_PROGRESS"}),
    )
    assert response.status_code == 422


def test_created_match_survives_new_session(two_teams: tuple[Team, Team]) -> None:
    team_1, team_2 = two_teams
    response = client.post(MATCHES_URL, json=_payload(team_1, team_2, fmt="ONE_DAY"))
    assert response.status_code == 201
    match_id = uuid.UUID(response.json()["id"])

    with SessionLocal() as fresh:
        persisted = fresh.scalar(select(Match).where(Match.id == match_id))
        assert persisted is not None
        assert persisted.format is MatchFormat.ONE_DAY
        assert persisted.overs == 50
        assert persisted.status is MatchStatus.CREATED
        assert persisted.team_1_id == team_1.id
        assert persisted.team_2_id == team_2.id
