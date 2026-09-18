"""Match and innings lifecycle API tests (Phase 8)."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.db.enums import InningsStatus, MatchFormat, MatchStatus
from app.db.models import Innings, Match, Team
from app.db.session import SessionLocal
from app.main import app
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match

client = TestClient(app)
MATCHES_URL = "/api/v1/matches"


@pytest.fixture()
def two_teams(db: Session) -> Generator[tuple[Team, Team], None, None]:
    suffix = uuid.uuid4().hex[:8]
    team_a = Team(
        name=f"Life Alpha {suffix}",
        short_code=f"X{suffix[:7]}",
        flag_url=f"https://example.test/flags/x-a-{suffix}.svg",
    )
    team_b = Team(
        name=f"Life Beta {suffix}",
        short_code=f"Y{suffix[:7]}",
        flag_url=f"https://example.test/flags/x-b-{suffix}.svg",
    )
    db.add_all([team_a, team_b])
    db.commit()
    db.refresh(team_a)
    db.refresh(team_b)
    yield team_a, team_b
    db.execute(
        delete(Innings).where(
            Innings.match_id.in_(
                select(Match.id).where(
                    Match.team_1_id.in_([team_a.id, team_b.id])
                    | Match.team_2_id.in_([team_a.id, team_b.id])
                )
            )
        )
    )
    db.execute(
        delete(Match).where(
            Match.team_1_id.in_([team_a.id, team_b.id])
            | Match.team_2_id.in_([team_a.id, team_b.id])
        )
    )
    db.execute(delete(Team).where(Team.id.in_([team_a.id, team_b.id])))
    db.commit()


def _create_match(
    db: Session,
    team_1: Team,
    team_2: Team,
    *,
    batting_first: Team | None = None,
) -> Match:
    return create_match(
        db,
        MatchCreateRequest(
            team_1_id=team_1.id,
            team_2_id=team_2.id,
            format=MatchFormat.T20,
            batting_first_team_id=(batting_first or team_1).id,
            overs=None,
        ),
    )


def test_start_match_creates_first_innings(
    two_teams: tuple[Team, Team], db: Session
) -> None:
    team_1, team_2 = two_teams
    match = _create_match(db, team_1, team_2, batting_first=team_1)

    response = client.post(f"{MATCHES_URL}/{match.id}/start")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == MatchStatus.IN_PROGRESS.value
    assert len(data["innings"]) == 1
    innings = data["innings"][0]
    assert innings["innings_number"] == 1
    assert innings["status"] == InningsStatus.IN_PROGRESS.value
    assert innings["batting_team"]["id"] == str(team_1.id)
    assert innings["bowling_team"]["id"] == str(team_2.id)

    innings_id = uuid.UUID(innings["id"])
    assert innings_id.version == 7
    row = db.execute(
        text("SELECT uuid_extract_version(id) FROM innings WHERE id = :id"),
        {"id": innings_id},
    ).scalar_one()
    assert row == 7


def test_start_match_rejects_duplicate_and_missing(
    two_teams: tuple[Team, Team], db: Session
) -> None:
    team_1, team_2 = two_teams
    match = _create_match(db, team_1, team_2)
    assert client.post(f"{MATCHES_URL}/{match.id}/start").status_code == 200
    again = client.post(f"{MATCHES_URL}/{match.id}/start")
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "INVALID_MATCH_TRANSITION"

    missing = client.post(f"{MATCHES_URL}/{uuid.uuid4()}/start")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "MATCH_NOT_FOUND"


def test_full_two_innings_lifecycle(
    two_teams: tuple[Team, Team], db: Session
) -> None:
    team_1, team_2 = two_teams
    match = _create_match(db, team_1, team_2, batting_first=team_1)

    started = client.post(f"{MATCHES_URL}/{match.id}/start").json()
    innings_1_id = started["innings"][0]["id"]

    completed_1 = client.post(f"/api/v1/innings/{innings_1_id}/complete")
    assert completed_1.status_code == 200
    body = completed_1.json()
    assert body["status"] == MatchStatus.INNINGS_BREAK.value
    assert body["innings"][0]["status"] == InningsStatus.COMPLETED.value
    assert len(body["innings"]) == 1

    # Duplicate complete rejected.
    dup = client.post(f"/api/v1/innings/{innings_1_id}/complete")
    assert dup.status_code == 409

    started_2 = client.post(f"{MATCHES_URL}/{match.id}/innings/start")
    assert started_2.status_code == 200
    body2 = started_2.json()
    assert body2["status"] == MatchStatus.IN_PROGRESS.value
    assert len(body2["innings"]) == 2
    second = body2["innings"][1]
    assert second["innings_number"] == 2
    assert second["status"] == InningsStatus.IN_PROGRESS.value
    assert second["batting_team"]["id"] == str(team_2.id)
    assert second["bowling_team"]["id"] == str(team_1.id)
    # Chase target is first-innings total + 1 (0 + 1 when no deliveries scored).
    assert second["target"] == body2["innings"][0]["innings_total_runs"] + 1

    # Duplicate next-innings start rejected.
    assert client.post(f"{MATCHES_URL}/{match.id}/innings/start").status_code == 409

    # Third innings rejected after break would require completing again first —
    # after final complete, match is COMPLETED.
    final = client.post(f"/api/v1/innings/{second['id']}/complete")
    assert final.status_code == 200
    done = final.json()
    assert done["status"] == MatchStatus.COMPLETED.value
    assert all(i["status"] == InningsStatus.COMPLETED.value for i in done["innings"])

    assert client.post(f"{MATCHES_URL}/{match.id}/start").status_code == 409
    assert client.post(f"{MATCHES_URL}/{match.id}/innings/start").status_code == 409


def test_invalid_transitions_rejected(
    two_teams: tuple[Team, Team], db: Session
) -> None:
    team_1, team_2 = two_teams
    match = _create_match(db, team_1, team_2)

    # CREATED cannot complete a nonexistent innings / start next.
    assert client.post(f"{MATCHES_URL}/{match.id}/innings/start").status_code == 409

    # Fabricate an innings id that doesn't exist.
    assert (
        client.post(f"/api/v1/innings/{uuid.uuid4()}/complete").status_code == 404
    )

    started = client.post(f"{MATCHES_URL}/{match.id}/start").json()
    # Cannot start next while IN_PROGRESS.
    assert client.post(f"{MATCHES_URL}/{match.id}/innings/start").status_code == 409

    client.post(f"/api/v1/innings/{started['innings'][0]['id']}/complete")
    # From break, cannot start a third after second is already created later —
    # after one break, start second, complete, then try third:
    client.post(f"{MATCHES_URL}/{match.id}/innings/start")
    # Force another break isn't possible without completing; after complete match done.
    # Explicit: max innings — complete second then try start next.
    detail = client.get(f"{MATCHES_URL}/{match.id}").json()
    innings_2 = next(i for i in detail["innings"] if i["innings_number"] == 2)
    client.post(f"/api/v1/innings/{innings_2['id']}/complete")
    third = client.post(f"{MATCHES_URL}/{match.id}/innings/start")
    assert third.status_code == 409


def test_concurrent_start_does_not_duplicate_innings(
    two_teams: tuple[Team, Team], db: Session
) -> None:
    team_1, team_2 = two_teams
    match = _create_match(db, team_1, team_2)
    match_id = str(match.id)

    def _start() -> int:
        with TestClient(app) as local:
            return local.post(f"{MATCHES_URL}/{match_id}/start").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: _start(), range(2)))

    assert sorted(codes) in ([200, 409], [409, 200], [200, 200])
    # Even if both returned 200 under rare timing, DB must have exactly one innings.
    # Prefer asserting DB invariant.
    with SessionLocal() as session:
        innings = list(
            session.scalars(
                select(Innings).where(Innings.match_id == uuid.UUID(match_id))
            )
        )
        assert len(innings) == 1
        assert innings[0].status is InningsStatus.IN_PROGRESS
        assert sum(1 for c in codes if c == 200) >= 1
