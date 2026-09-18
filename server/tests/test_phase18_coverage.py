"""Phase 18 — domain invariants, reconstruction, Socket room isolation."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.db.enums import DeliveryType, InningsStatus, MatchFormat, MatchStatus
from app.db.models import BatterReplacement, Delivery, Innings, Match, Player, Team
from app.db.seed import seed_database
from app.main import app
from app.realtime.socket import match_room
from app.realtime.versions import reset_versions_for_tests
from app.schemas.delivery import DeliveryCreateRequest
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match, start_match, start_next_innings
from app.services.reconstruction import reconstruct_innings_state
from app.services.scoring import submit_delivery

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


def _cleanup_match(db: Session, match_id: uuid.UUID) -> None:
    innings_ids = list(db.scalars(select(Innings.id).where(Innings.match_id == match_id)))
    if innings_ids:
        db.execute(
            delete(BatterReplacement).where(BatterReplacement.innings_id.in_(innings_ids))
        )
        db.execute(delete(Delivery).where(Delivery.innings_id.in_(innings_ids)))
        db.execute(delete(Innings).where(Innings.id.in_(innings_ids)))
    db.execute(delete(Match).where(Match.id == match_id))
    db.commit()


def _delivery(
    striker: Player,
    non_striker: Player,
    bowler: Player,
    *,
    delivery_type: DeliveryType = DeliveryType.NORMAL,
    bat_runs: int = 0,
    extra_runs: int | None = None,
) -> DeliveryCreateRequest:
    return DeliveryCreateRequest(
        striker_id=striker.id,
        non_striker_id=non_striker.id,
        bowler_id=bowler.id,
        delivery_type=delivery_type,
        bat_runs=bat_runs,
        extra_runs=extra_runs,
    )


def test_match_has_exactly_two_innings_capacity(
    db: Session, seeded: tuple[Team, Team, Player, Player, Player]
) -> None:
    """Limited-overs matches support exactly two innings; a third start conflicts."""
    india, pakistan, striker, non_striker, bowler = seeded
    match = create_match(
        db,
        MatchCreateRequest(
            team_1_id=india.id,
            team_2_id=pakistan.id,
            format=MatchFormat.CUSTOM,
            batting_first_team_id=india.id,
            overs=1,
        ),
    )
    match = start_match(db, match.id)
    assert len(match.innings) == 1

    innings = next(i for i in match.innings if i.innings_number == 1)
    for _ in range(6):
        submit_delivery(
            db,
            innings.id,
            _delivery(striker, non_striker, bowler, bat_runs=0),
        )
    db.refresh(innings)
    db.refresh(match)
    assert innings.status == InningsStatus.COMPLETED
    assert match.status == MatchStatus.INNINGS_BREAK

    match = start_next_innings(db, match.id)
    assert len(match.innings) == 2
    assert {i.innings_number for i in match.innings} == {1, 2}

    # Duplicate start while IN_PROGRESS is rejected (still only two innings).
    dup = client.post(f"/api/v1/matches/{match.id}/innings/start")
    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "INVALID_MATCH_TRANSITION"

    innings_2 = next(i for i in match.innings if i.innings_number == 2)
    completed = client.post(f"/api/v1/innings/{innings_2.id}/complete")
    assert completed.status_code == 200
    assert completed.json()["status"] == MatchStatus.COMPLETED.value

    # After both innings, a further start cannot create a third innings.
    third = client.post(f"/api/v1/matches/{match.id}/innings/start")
    assert third.status_code == 409
    assert third.json()["detail"]["code"] == "INVALID_MATCH_TRANSITION"

    count = db.scalar(
        select(func.count()).select_from(Innings).where(Innings.match_id == match.id)
    )
    assert count == 2
    _cleanup_match(db, match.id)


def test_created_entities_are_uuid_version_7_in_postgres(
    db: Session, seeded: tuple[Team, Team, Player, Player, Player]
) -> None:
    india, pakistan, striker, non_striker, bowler = seeded
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
    delivery = submit_delivery(
        db,
        innings.id,
        _delivery(striker, non_striker, bowler, bat_runs=1),
    )
    delivery_id = (
        delivery.id if isinstance(delivery.id, uuid.UUID) else uuid.UUID(str(delivery.id))
    )

    for entity_id, table in (
        (match.id, "matches"),
        (innings.id, "innings"),
        (delivery_id, "deliveries"),
        (india.id, "teams"),
        (striker.id, "players"),
    ):
        ver = db.execute(
            text(f"SELECT uuid_extract_version(id) FROM {table} WHERE id = :id"),
            {"id": entity_id},
        ).scalar_one()
        assert int(ver) == 7, f"{table} id not UUIDv7"
        assert entity_id.version == 7

    _cleanup_match(db, match.id)


def test_reconstruct_empty_and_after_deliveries(
    db: Session,
    started_match: tuple[Match, Innings, tuple[Team, Team, Player, Player, Player]],
) -> None:
    match, innings, (_india, _pakistan, striker, non_striker, bowler) = started_match

    empty = reconstruct_innings_state(db, innings, match)
    assert empty.delivery_count == 0
    assert empty.legal_delivery_count == 0
    assert empty.innings_total_runs == 0
    assert empty.free_hit_pending is False
    assert empty.replacement_required is False

    submit_delivery(
        db,
        innings.id,
        _delivery(striker, non_striker, bowler, delivery_type=DeliveryType.NO_BALL, bat_runs=0),
    )
    db.refresh(innings)
    after_nb = reconstruct_innings_state(db, innings, match)
    assert after_nb.delivery_count == 1
    assert after_nb.legal_delivery_count == 0
    assert after_nb.free_hit_pending is True
    assert after_nb.innings_total_runs == 1

    submit_delivery(
        db,
        innings.id,
        _delivery(striker, non_striker, bowler, bat_runs=4),
    )
    db.refresh(innings)
    after = reconstruct_innings_state(db, innings, match)
    assert after.delivery_count == 2
    assert after.legal_delivery_count == 1
    assert after.free_hit_pending is False
    assert after.innings_total_runs == 5


def test_publish_targets_match_specific_room_only(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    seeded: tuple[Team, Team, Player, Player, Player],
) -> None:
    """Room isolation: emit must target match:{id}, never a different match room."""
    india, pakistan, striker, non_striker, bowler = seeded
    match_a = create_match(
        db,
        MatchCreateRequest(
            team_1_id=india.id,
            team_2_id=pakistan.id,
            format=MatchFormat.T20,
            batting_first_team_id=india.id,
            overs=None,
        ),
    )
    match_a = start_match(db, match_a.id)
    match_b = create_match(
        db,
        MatchCreateRequest(
            team_1_id=india.id,
            team_2_id=pakistan.id,
            format=MatchFormat.T20,
            batting_first_team_id=pakistan.id,
            overs=None,
        ),
    )
    match_b = start_match(db, match_b.id)

    emitted_rooms: list[str] = []

    async def capture_emit(event: str, data=None, **kwargs):
        room = kwargs.get("room")
        if room is not None:
            emitted_rooms.append(str(room))

    monkeypatch.setattr("app.realtime.socket.sio.emit", capture_emit)

    from app.realtime.socket import _emit_match_update

    asyncio.run(
        _emit_match_update(
            {
                "match_id": str(match_a.id),
                "version": 1,
                "match": {},
                "deliveries_by_innings": {},
            }
        )
    )
    asyncio.run(
        _emit_match_update(
            {
                "match_id": str(match_b.id),
                "version": 1,
                "match": {},
                "deliveries_by_innings": {},
            }
        )
    )

    assert emitted_rooms == [match_room(match_a.id), match_room(match_b.id)]
    assert emitted_rooms[0] != emitted_rooms[1]

    published_innings: list[uuid.UUID] = []

    def spy(_session: Session, innings_id: uuid.UUID) -> None:
        published_innings.append(innings_id)

    import app.realtime as realtime_mod

    monkeypatch.setattr(realtime_mod, "publish_match_update_from_innings", spy)

    innings_a = next(i for i in match_a.innings if i.innings_number == 1)
    innings_b = next(i for i in match_b.innings if i.innings_number == 1)
    response = client.post(
        f"/api/v1/innings/{innings_a.id}/deliveries",
        json={
            "striker_id": str(striker.id),
            "non_striker_id": str(non_striker.id),
            "bowler_id": str(bowler.id),
            "delivery_type": "NORMAL",
            "bat_runs": 1,
        },
    )
    assert response.status_code == 200
    assert published_innings == [innings_a.id]
    assert innings_b.id not in published_innings

    _cleanup_match(db, match_a.id)
    _cleanup_match(db, match_b.id)


def test_structured_error_contract_shape() -> None:
    response = client.get(f"/api/v1/matches/{uuid.uuid4()}")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert "code" in detail and "message" in detail
    assert isinstance(detail["code"], str)
    assert isinstance(detail["message"], str)
    assert "Traceback" not in detail["message"]
    assert "X-Request-ID" in response.headers
