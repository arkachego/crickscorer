"""Socket.IO live-update tests (Phase 15)."""

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
from app.realtime.snapshot import build_match_live_snapshot
from app.realtime.versions import bump_match_version, reset_versions_for_tests
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match, start_match

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_versions() -> Generator[None, None, None]:
    reset_versions_for_tests()
    yield
    reset_versions_for_tests()


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


def test_health_still_ok_through_socketio_asgi() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_monotonic() -> None:
    mid = uuid.uuid4()
    assert bump_match_version(mid) == 1
    assert bump_match_version(mid) == 2


def test_snapshot_contains_authoritative_fields(
    db: Session,
    started: tuple[Match, Innings, tuple[Team, Team, Player, Player, Player]],
) -> None:
    match, innings, sides = started
    _, _, striker, non_striker, bowler = sides
    assert (
        client.post(
            f"/api/v1/innings/{innings.id}/deliveries",
            json={
                "striker_id": str(striker.id),
                "non_striker_id": str(non_striker.id),
                "bowler_id": str(bowler.id),
                "delivery_type": "NORMAL",
                "bat_runs": 4,
            },
        ).status_code
        == 200
    )
    snap = build_match_live_snapshot(db, match.id, bump=True)
    assert snap["match_id"] == str(match.id)
    assert snap["version"] >= 1
    assert "match" in snap
    assert str(innings.id) in snap["deliveries_by_innings"]
    inn = next(i for i in snap["match"]["innings"] if i["id"] == str(innings.id))
    assert inn["innings_total_runs"] == 4
    assert inn["legal_delivery_count"] == 1


def test_successful_delivery_publishes_update(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    started: tuple[Match, Innings, tuple[Team, Team, Player, Player, Player]],
) -> None:
    match, innings, sides = started
    _, _, striker, non_striker, bowler = sides
    published: list[uuid.UUID] = []

    def spy(_session: Session, innings_id: uuid.UUID) -> None:
        published.append(innings_id)

    import app.realtime as realtime_mod

    monkeypatch.setattr(realtime_mod, "publish_match_update_from_innings", spy)

    response = client.post(
        f"/api/v1/innings/{innings.id}/deliveries",
        json={
            "striker_id": str(striker.id),
            "non_striker_id": str(non_striker.id),
            "bowler_id": str(bowler.id),
            "delivery_type": "NORMAL",
            "bat_runs": 6,
        },
    )
    assert response.status_code == 200
    assert published == [innings.id]


def test_failed_delivery_does_not_publish(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    started: tuple[Match, Innings, tuple[Team, Team, Player, Player, Player]],
) -> None:
    _, innings, sides = started
    _, _, striker, non_striker, bowler = sides
    published: list[uuid.UUID] = []

    def spy(_session: Session, innings_id: uuid.UUID) -> None:
        published.append(innings_id)

    import app.realtime as realtime_mod

    monkeypatch.setattr(realtime_mod, "publish_match_update_from_innings", spy)

    response = client.post(
        f"/api/v1/innings/{innings.id}/deliveries",
        json={
            "striker_id": str(striker.id),
            "non_striker_id": str(striker.id),  # invalid: same player
            "bowler_id": str(bowler.id),
            "delivery_type": "NORMAL",
            "bat_runs": 1,
        },
    )
    assert response.status_code in {400, 409, 422}
    assert published == []


def test_lifecycle_start_publishes(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    seeded: tuple[Team, Team, Player, Player, Player],
) -> None:
    india, pakistan, *_ = seeded
    published: list[uuid.UUID] = []

    def spy(match_id: uuid.UUID) -> None:
        published.append(match_id)

    import app.realtime as realtime_mod

    monkeypatch.setattr(realtime_mod, "publish_match_update", spy)

    created = create_match(
        db,
        MatchCreateRequest(
            team_1_id=india.id,
            team_2_id=pakistan.id,
            format=MatchFormat.T20,
            batting_first_team_id=india.id,
            overs=None,
        ),
    )
    response = client.post(f"/api/v1/matches/{created.id}/start")
    assert response.status_code == 200
    assert created.id in published

    match_id = created.id
    innings_ids = list(db.scalars(select(Innings.id).where(Innings.match_id == match_id)))
    if innings_ids:
        db.execute(delete(Delivery).where(Delivery.innings_id.in_(innings_ids)))
        db.execute(delete(Innings).where(Innings.id.in_(innings_ids)))
    db.execute(delete(Match).where(Match.id == match_id))
    db.commit()


def test_match_join_validates_and_emits(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    started: tuple[Match, Innings, tuple[Team, Team, Player, Player, Player]],
) -> None:
    import asyncio

    match, _, _ = started
    emitted: list[tuple[str, dict]] = []

    async def fake_emit(event: str, data=None, **kwargs):
        emitted.append((event, data if isinstance(data, dict) else {}))

    async def fake_enter_room(sid: str, room: str):
        return None

    async def fake_leave_room(sid: str, room: str):
        return None

    def fake_rooms(sid: str):
        return [sid]

    monkeypatch.setattr("app.realtime.socket.sio.emit", fake_emit)
    monkeypatch.setattr("app.realtime.socket.sio.enter_room", fake_enter_room)
    monkeypatch.setattr("app.realtime.socket.sio.leave_room", fake_leave_room)
    monkeypatch.setattr("app.realtime.socket.sio.rooms", fake_rooms)

    from app.realtime.socket import match_join

    asyncio.run(match_join("sid-1", {"match_id": "not-a-uuid"}))
    assert emitted[-1][0] == "match:error"
    assert emitted[-1][1]["code"] == "INVALID_MATCH_ID"

    emitted.clear()
    asyncio.run(match_join("sid-1", {"match_id": str(uuid.uuid4())}))
    assert emitted[-1][0] == "match:error"
    assert emitted[-1][1]["code"] == "MATCH_NOT_FOUND"

    emitted.clear()
    asyncio.run(match_join("sid-1", {"match_id": str(match.id)}))
    assert emitted[-1][0] == "match:joined"
    assert emitted[-1][1]["match_id"] == str(match.id)
    assert "match" in emitted[-1][1]
