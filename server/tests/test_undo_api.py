"""Undo + state reconstruction tests (Phase 12)."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import InningsStatus, MatchFormat, MatchStatus
from app.db.models import BatterReplacement, Delivery, Innings, Match, Player, Team
from app.db.seed import seed_database
from app.db.session import SessionLocal
from app.main import app
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match, start_match

client = TestClient(app)


@dataclass
class SeededSides:
    india: Team
    pakistan: Team
    striker: Player
    non_striker: Player
    bowler: Player
    replacement: Player
    india_xi: list[Player]


@pytest.fixture()
def seeded(db: Session) -> SeededSides:
    seed_database(db)
    india = db.scalar(select(Team).where(Team.short_code == "IND"))
    pakistan = db.scalar(select(Team).where(Team.short_code == "PAK"))
    assert india and pakistan

    def by_name(team_id: uuid.UUID, name: str) -> Player:
        p = db.scalar(select(Player).where(Player.team_id == team_id, Player.name == name))
        assert p is not None
        return p

    xi = list(
        db.scalars(
            select(Player)
            .where(Player.team_id == india.id, Player.batting_order.is_not(None))
            .order_by(Player.batting_order)
        )
    )
    return SeededSides(
        india=india,
        pakistan=pakistan,
        striker=by_name(india.id, "Abhishek Sharma"),
        non_striker=by_name(india.id, "Shubman Gill"),
        bowler=by_name(pakistan.id, "Shaheen Afridi"),
        replacement=by_name(india.id, "Suryakumar Yadav"),
        india_xi=xi,
    )


def _cleanup(db: Session, match_id: uuid.UUID) -> None:
    innings_ids = list(db.scalars(select(Innings.id).where(Innings.match_id == match_id)))
    if innings_ids:
        db.execute(
            delete(BatterReplacement).where(BatterReplacement.innings_id.in_(innings_ids))
        )
        db.execute(delete(Delivery).where(Delivery.innings_id.in_(innings_ids)))
        db.execute(delete(Innings).where(Innings.id.in_(innings_ids)))
    db.execute(delete(Match).where(Match.id == match_id))
    db.commit()


@pytest.fixture()
def started(
    db: Session, seeded: SeededSides
) -> Generator[tuple[Match, Innings, SeededSides], None, None]:
    match = create_match(
        db,
        MatchCreateRequest(
            team_1_id=seeded.india.id,
            team_2_id=seeded.pakistan.id,
            format=MatchFormat.CUSTOM,
            batting_first_team_id=seeded.india.id,
            overs=5,
        ),
    )
    match = start_match(db, match.id)
    innings = match.innings[0]
    yield match, innings, seeded
    _cleanup(db, match.id)


def _base(sides: SeededSides, *, striker: Player | None = None, non: Player | None = None) -> dict:
    return {
        "striker_id": str((striker or sides.striker).id),
        "non_striker_id": str((non or sides.non_striker).id),
        "bowler_id": str(sides.bowler.id),
    }


def _post(innings_id: uuid.UUID, body: dict):
    return client.post(f"/api/v1/innings/{innings_id}/deliveries", json=body)


def _undo(innings_id: uuid.UUID):
    return client.post(f"/api/v1/innings/{innings_id}/undo")


def test_undo_no_deliveries(started: tuple[Match, Innings, SeededSides]) -> None:
    _, innings, _ = started
    resp = _undo(innings.id)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "NO_DELIVERY_TO_UNDO"


def test_undo_normal_sequence(
    started: tuple[Match, Innings, SeededSides], db: Session
) -> None:
    _, innings, sides = started
    for runs in (1, 2, 4):
        assert _post(
            innings.id, {**_base(sides), "delivery_type": "NORMAL", "bat_runs": runs}
        ).status_code == 200

    undone = _undo(innings.id)
    assert undone.status_code == 200
    body = undone.json()
    assert body["delivery_count"] == 2
    assert body["innings_total_runs"] == 3
    assert body["legal_delivery_count"] == 2
    assert body["free_hit_pending"] is False

    seqs = list(
        db.scalars(
            select(Delivery.sequence_no)
            .where(Delivery.innings_id == innings.id)
            .order_by(Delivery.sequence_no)
        )
    )
    assert seqs == [1, 2]

    nxt = _post(innings.id, {**_base(sides), "delivery_type": "NORMAL", "bat_runs": 0}).json()
    assert nxt["sequence_no"] == 3


def test_undo_wide_and_no_ball_free_hit(
    started: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started
    _post(innings.id, {**_base(sides), "delivery_type": "NORMAL", "bat_runs": 0})
    _post(
        innings.id,
        {**_base(sides), "delivery_type": "WIDE", "bat_runs": 0, "extra_runs": 1},
    )
    assert _undo(innings.id).json()["legal_delivery_count"] == 1

    _post(innings.id, {**_base(sides), "delivery_type": "NO_BALL", "bat_runs": 0})
    after_nb = _undo(innings.id).json()
    assert after_nb["free_hit_pending"] is False
    assert after_nb["legal_delivery_count"] == 1

    _post(innings.id, {**_base(sides), "delivery_type": "NO_BALL", "bat_runs": 1})
    fh = _post(innings.id, {**_base(sides), "delivery_type": "NORMAL", "bat_runs": 0}).json()
    assert fh["is_free_hit"] is True
    undone = _undo(innings.id).json()
    assert undone["free_hit_pending"] is True
    assert undone["delivery_count"] == 2  # normal + no-ball remaining? started with 1 normal, then nb, then fh normal; undo fh → 1 normal + 1 nb = 2, and before that we undid wide. Wait.

    # Recount from this test alone after previous undos left 1 normal.
    # After undo fh: deliveries = [NORMAL0, NO_BALL], free_hit pending True.


def test_undo_wicket_and_replacement(
    started: tuple[Match, Innings, SeededSides], db: Session
) -> None:
    _, innings, sides = started
    _post(
        innings.id,
        {
            **_base(sides),
            "delivery_type": "NORMAL",
            "bat_runs": 0,
            "wicket": {
                "dismissed_player_id": str(sides.striker.id),
                "dismissal_type": "BOWLED",
            },
        },
    )
    assert (
        client.post(
            f"/api/v1/innings/{innings.id}/replacement",
            json={"player_id": str(sides.replacement.id)},
        ).status_code
        == 200
    )
    _post(
        innings.id,
        {
            **_base(sides, striker=sides.replacement, non=sides.non_striker),
            "delivery_type": "NORMAL",
            "bat_runs": 1,
        },
    )

    # Undo post-replacement delivery → C + B still active
    body = _undo(innings.id).json()
    assert body["delivery_count"] == 1
    assert body["replacement_required"] is False
    active = {body["striker"]["id"], body["non_striker"]["id"]}
    assert str(sides.replacement.id) in active
    assert str(sides.non_striker.id) in active
    assert str(sides.striker.id) not in active

    # Undo wicket → A + B restored, replacement gone
    body2 = _undo(innings.id).json()
    assert body2["delivery_count"] == 0
    assert body2["replacement_required"] is False
    assert body2["striker"] is None and body2["non_striker"] is None
    assert body2["innings_status"] == InningsStatus.IN_PROGRESS.value
    assert (
        db.scalar(
            select(func.count())
            .select_from(BatterReplacement)
            .where(BatterReplacement.innings_id == innings.id)
        )
        == 0
    )


def test_undo_overs_completion(db: Session, seeded: SeededSides) -> None:
    match = create_match(
        db,
        MatchCreateRequest(
            team_1_id=seeded.india.id,
            team_2_id=seeded.pakistan.id,
            format=MatchFormat.CUSTOM,
            batting_first_team_id=seeded.india.id,
            overs=1,
        ),
    )
    match = start_match(db, match.id)
    iid = match.innings[0].id
    for _ in range(6):
        assert _post(
            iid, {**_base(seeded), "delivery_type": "NORMAL", "bat_runs": 0}
        ).status_code == 200
    assert client.get(f"/api/v1/matches/{match.id}").json()["status"] == "INNINGS_BREAK"

    undone = _undo(iid).json()
    assert undone["innings_status"] == "IN_PROGRESS"
    assert undone["match_status"] == "IN_PROGRESS"
    assert undone["legal_delivery_count"] == 5

    final = _post(iid, {**_base(seeded), "delivery_type": "NORMAL", "bat_runs": 0}).json()
    assert final["innings_status"] == "COMPLETED"
    assert final["match_status"] == "INNINGS_BREAK"
    _cleanup(db, match.id)


def test_concurrent_undo_once(
    started: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started
    _post(innings.id, {**_base(sides), "delivery_type": "NORMAL", "bat_runs": 1})
    iid = str(innings.id)

    def _one() -> int:
        with TestClient(app) as local:
            return local.post(f"/api/v1/innings/{iid}/undo").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: _one(), range(2)))
    assert sorted(codes) in ([200, 409], [409, 200])
    with SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Delivery)
                .where(Delivery.innings_id == innings.id)
            )
            == 0
        )
