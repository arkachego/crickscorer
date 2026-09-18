"""Extras + Free Hit scoring tests (Phase 10)."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import DeliveryType, InningsStatus, MatchFormat, MatchStatus
from app.db.models import Delivery, Innings, Match, Player, Team
from app.db.seed import seed_database
from app.db.session import SessionLocal
from app.main import app
from app.schemas.delivery import DeliveryCreateRequest
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match, start_match
from app.services.scoring import submit_delivery

client = TestClient(app)


@dataclass(frozen=True)
class SeededSides:
    india: Team
    pakistan: Team
    striker: Player
    non_striker: Player
    bowler: Player


@pytest.fixture()
def seeded(db: Session) -> SeededSides:
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
        assert player is not None, name
        return player

    return SeededSides(
        india=india,
        pakistan=pakistan,
        striker=by_name(india.id, "Abhishek Sharma"),
        non_striker=by_name(india.id, "Shubman Gill"),
        bowler=by_name(pakistan.id, "Shaheen Afridi"),
    )


def _cleanup_match(db: Session, match_id: uuid.UUID) -> None:
    innings_ids = list(
        db.scalars(select(Innings.id).where(Innings.match_id == match_id))
    )
    if innings_ids:
        db.execute(delete(Delivery).where(Delivery.innings_id.in_(innings_ids)))
        db.execute(delete(Innings).where(Innings.id.in_(innings_ids)))
    db.execute(delete(Match).where(Match.id == match_id))
    db.commit()


@pytest.fixture()
def started_one_over(
    db: Session, seeded: SeededSides
) -> Generator[tuple[Match, Innings, SeededSides], None, None]:
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
    innings = next(i for i in match.innings if i.innings_number == 1)
    yield match, innings, seeded
    _cleanup_match(db, match.id)


@pytest.fixture()
def started_five_overs(
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
    innings = next(i for i in match.innings if i.innings_number == 1)
    yield match, innings, seeded
    _cleanup_match(db, match.id)


def _base(sides: SeededSides) -> dict[str, object]:
    return {
        "striker_id": str(sides.striker.id),
        "non_striker_id": str(sides.non_striker.id),
        "bowler_id": str(sides.bowler.id),
    }


def _post(innings_id: uuid.UUID, body: dict[str, object]):
    return client.post(f"/api/v1/innings/{innings_id}/deliveries", json=body)


def _normal(sides: SeededSides, bat_runs: int) -> dict[str, object]:
    return {**_base(sides), "delivery_type": "NORMAL", "bat_runs": bat_runs}


def _wide(sides: SeededSides, extra_runs: int) -> dict[str, object]:
    return {
        **_base(sides),
        "delivery_type": "WIDE",
        "bat_runs": 0,
        "extra_runs": extra_runs,
    }


def _no_ball(sides: SeededSides, bat_runs: int) -> dict[str, object]:
    return {**_base(sides), "delivery_type": "NO_BALL", "bat_runs": bat_runs}


def _bye(sides: SeededSides, extra_runs: int) -> dict[str, object]:
    return {
        **_base(sides),
        "delivery_type": "BYE",
        "bat_runs": 0,
        "extra_runs": extra_runs,
    }


def _leg_bye(sides: SeededSides, extra_runs: int) -> dict[str, object]:
    return {
        **_base(sides),
        "delivery_type": "LEG_BYE",
        "bat_runs": 0,
        "extra_runs": extra_runs,
    }


# --- Wides ---


def test_wide_semantics(
    started_five_overs: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started_five_overs
    one = _post(innings.id, _wide(sides, 1))
    assert one.status_code == 200
    data = one.json()
    assert data["delivery_type"] == "WIDE"
    assert data["wide_runs"] == 1
    assert data["bat_runs"] == 0
    assert data["total_runs"] == 1
    assert data["is_legal"] is False
    assert data["sequence_no"] == 1
    assert data["over_number"] == 0
    assert data["ball_in_over"] == 1
    assert data["is_free_hit"] is False

    multi = _post(innings.id, _wide(sides, 3))
    assert multi.status_code == 200
    m = multi.json()
    assert m["wide_runs"] == 3
    assert m["total_runs"] == 3
    assert m["is_legal"] is False
    assert m["sequence_no"] == 2
    assert m["ball_in_over"] == 1  # still ball 1
    assert m["innings_total_runs"] == 4

    # Legal advances to ball 1 still (first legal)
    legal = _post(innings.id, _normal(sides, 1)).json()
    assert legal["is_legal"] is True
    assert legal["sequence_no"] == 3
    assert legal["ball_in_over"] == 1

    assert _post(innings.id, _wide(sides, 0)).status_code == 422
    assert _post(
        innings.id,
        {**_base(sides), "delivery_type": "WIDE", "bat_runs": 4, "extra_runs": 1},
    ).status_code == 422


# --- No-ball ---


@pytest.mark.parametrize("bat_runs", [0, 1, 2, 3, 4, 6])
def test_no_ball_semantics(
    started_five_overs: tuple[Match, Innings, SeededSides],
    bat_runs: int,
) -> None:
    _, innings, sides = started_five_overs
    data = _post(innings.id, _no_ball(sides, bat_runs)).json()
    assert data["delivery_type"] == "NO_BALL"
    assert data["no_ball_runs"] == 1
    assert data["bat_runs"] == bat_runs
    assert data["total_runs"] == 1 + bat_runs
    assert data["is_legal"] is False
    assert data["ball_in_over"] == 1


def test_no_ball_does_not_advance_and_rejects_extras(
    started_five_overs: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started_five_overs
    _post(innings.id, _normal(sides, 0))
    nb = _post(innings.id, _no_ball(sides, 4)).json()
    assert nb["sequence_no"] == 2
    assert nb["ball_in_over"] == 2
    nxt = _post(innings.id, _normal(sides, 0)).json()
    assert nxt["sequence_no"] == 3
    assert nxt["ball_in_over"] == 2  # no-ball did not consume
    assert nxt["is_free_hit"] is True

    assert (
        _post(
            innings.id,
            {
                **_base(sides),
                "delivery_type": "NO_BALL",
                "bat_runs": 0,
                "extra_runs": 1,
            },
        ).status_code
        == 422
    )


# --- Bye / Leg-bye ---


def test_bye_and_leg_bye(
    started_five_overs: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started_five_overs
    bye = _post(innings.id, _bye(sides, 2)).json()
    assert bye["delivery_type"] == "BYE"
    assert bye["bye_runs"] == 2
    assert bye["bat_runs"] == 0
    assert bye["total_runs"] == 2
    assert bye["is_legal"] is True
    assert bye["ball_in_over"] == 1

    leg = _post(innings.id, _leg_bye(sides, 3)).json()
    assert leg["delivery_type"] == "LEG_BYE"
    assert leg["leg_bye_runs"] == 3
    assert leg["total_runs"] == 3
    assert leg["is_legal"] is True
    assert leg["ball_in_over"] == 2
    assert leg["innings_total_runs"] == 5

    assert _post(innings.id, _bye(sides, 0)).status_code == 422
    assert _post(innings.id, _leg_bye(sides, 0)).status_code == 422
    assert (
        _post(
            innings.id,
            {**_base(sides), "delivery_type": "BYE", "bat_runs": 2, "extra_runs": 1},
        ).status_code
        == 422
    )
    assert (
        _post(
            innings.id,
            {
                **_base(sides),
                "delivery_type": "LEG_BYE",
                "bat_runs": 3,
                "extra_runs": 1,
            },
        ).status_code
        == 422
    )


# --- Mixed progression ---


def test_mixed_legal_illegal_progression(
    started_five_overs: tuple[Match, Innings, SeededSides],
    db: Session,
) -> None:
    _, innings, sides = started_five_overs
    # NORMAL, WIDE, NORMAL, NO_BALL, BYE, LEG_BYE, NORMAL
    seq = [
        _normal(sides, 1),
        _wide(sides, 1),
        _normal(sides, 2),
        _no_ball(sides, 0),
        _bye(sides, 1),
        _leg_bye(sides, 1),
        _normal(sides, 0),
    ]
    # After each: (sequence, over, ball, is_legal, innings_total)
    expected = [
        (1, 0, 1, True, 1),
        (2, 0, 2, False, 2),
        (3, 0, 2, True, 4),
        (4, 0, 3, False, 5),
        (5, 0, 3, True, 6),
        (6, 0, 4, True, 7),
        (7, 0, 5, True, 7),
    ]
    for body, (seq_no, over, ball, legal, total) in zip(seq, expected, strict=True):
        data = _post(innings.id, body).json()
        assert data["sequence_no"] == seq_no
        assert data["over_number"] == over
        assert data["ball_in_over"] == ball
        assert data["is_legal"] is legal
        assert data["innings_total_runs"] == total

    # 5 legal + 3 wides + 2 no-balls still not over; then 1 legal completes over
    for _ in range(3):
        _post(innings.id, _wide(sides, 1))
    for _ in range(2):
        _post(innings.id, _no_ball(sides, 0))
    # legal count still 5
    fin = _post(innings.id, _normal(sides, 0)).json()
    assert fin["ball_in_over"] == 6
    assert fin["over_number"] == 0
    nxt = _post(innings.id, _normal(sides, 1)).json()
    assert nxt["over_number"] == 1
    assert nxt["ball_in_over"] == 1

    ordered = list(
        db.scalars(
            select(Delivery)
            .where(Delivery.innings_id == innings.id)
            .order_by(Delivery.sequence_no, Delivery.id)
        )
    )
    assert [d.sequence_no for d in ordered] == list(range(1, len(ordered) + 1))


# --- Configured overs with illegals ---


def test_completion_uses_legal_count_only(
    started_one_over: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started_one_over
    for _ in range(5):
        assert _post(innings.id, _normal(sides, 0)).status_code == 200

    # Case B: many wides do not complete
    for _ in range(20):
        w = _post(innings.id, _wide(sides, 1))
        assert w.status_code == 200
        assert w.json()["innings_status"] == InningsStatus.IN_PROGRESS.value

    # Case C: next legal completes
    done = _post(innings.id, _normal(sides, 1))
    assert done.status_code == 200
    body = done.json()
    assert body["innings_status"] == InningsStatus.COMPLETED.value
    assert body["match_status"] == MatchStatus.INNINGS_BREAK.value
    assert body["is_legal"] is True


def test_six_legal_completes_one_over_innings(
    db: Session, seeded: SeededSides
) -> None:
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
    innings_id = match.innings[0].id
    for _ in range(5):
        _post(innings_id, _normal(seeded, 0))
    final = _post(innings_id, _normal(seeded, 0)).json()
    assert final["innings_status"] == "COMPLETED"
    assert final["match_status"] == "INNINGS_BREAK"
    _cleanup_match(db, match.id)


# --- Free Hit ---


def test_free_hit_lifecycle(
    started_five_overs: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started_five_overs
    normal = _post(innings.id, _normal(sides, 0)).json()
    assert normal["is_free_hit"] is False

    nb = _post(innings.id, _no_ball(sides, 0)).json()
    assert nb["is_free_hit"] is False
    assert nb["no_ball_runs"] == 1

    fh = _post(innings.id, _normal(sides, 4)).json()
    assert fh["is_free_hit"] is True
    assert fh["is_legal"] is True

    after = _post(innings.id, _normal(sides, 1)).json()
    assert after["is_free_hit"] is False

    # Free Hit may be wide (consumes), then no new free hit
    _post(innings.id, _no_ball(sides, 1))
    wide_fh = _post(innings.id, _wide(sides, 2)).json()
    assert wide_fh["is_free_hit"] is True
    assert wide_fh["is_legal"] is False
    nxt = _post(innings.id, _normal(sides, 0)).json()
    assert nxt["is_free_hit"] is False

    # Free Hit no-ball creates another Free Hit
    _post(innings.id, _no_ball(sides, 0))
    fh_nb = _post(innings.id, _no_ball(sides, 2)).json()
    assert fh_nb["is_free_hit"] is True
    assert fh_nb["no_ball_runs"] == 1
    again = _post(innings.id, _bye(sides, 1)).json()
    assert again["is_free_hit"] is True
    cleared = _post(innings.id, _normal(sides, 0)).json()
    assert cleared["is_free_hit"] is False

    # Client cannot submit is_free_hit
    assert (
        _post(
            innings.id,
            {**_normal(sides, 0), "is_free_hit": True},
        ).status_code
        == 422
    )


def test_concurrent_free_hit_not_duplicated(
    db: Session, seeded: SeededSides
) -> None:
    match = create_match(
        db,
        MatchCreateRequest(
            team_1_id=seeded.india.id,
            team_2_id=seeded.pakistan.id,
            format=MatchFormat.CUSTOM,
            batting_first_team_id=seeded.india.id,
            overs=2,
        ),
    )
    match = start_match(db, match.id)
    innings_id = match.innings[0].id
    assert _post(innings_id, _no_ball(seeded, 0)).status_code == 200

    body = _normal(seeded, 1)
    iid = str(innings_id)

    def _one() -> tuple[int, bool | None]:
        with TestClient(app) as local:
            resp = local.post(f"/api/v1/innings/{iid}/deliveries", json=body)
            if resp.status_code != 200:
                return resp.status_code, None
            return 200, resp.json()["is_free_hit"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: _one(), range(4)))

    ok = [r for r in results if r[0] == 200]
    assert len(ok) == 4
    free_hits = [flag for _, flag in ok if flag is True]
    # Exactly one delivery should consume the Free Hit opportunity.
    assert len(free_hits) == 1

    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(Delivery)
                .where(Delivery.innings_id == innings_id)
                .order_by(Delivery.sequence_no)
            )
        )
        assert rows[0].no_ball_runs == 1
        assert sum(1 for r in rows if r.is_free_hit) == 1
        assert [r.sequence_no for r in rows] == list(range(1, len(rows) + 1))

    _cleanup_match(db, match.id)


def test_invalid_combination_creates_no_delivery(
    started_five_overs: tuple[Match, Innings, SeededSides],
    db: Session,
) -> None:
    _, innings, sides = started_five_overs
    before = db.scalar(
        select(func.count()).select_from(Delivery).where(Delivery.innings_id == innings.id)
    )
    assert (
        _post(
            innings.id,
            {**_base(sides), "delivery_type": "WIDE", "bat_runs": 4, "extra_runs": 1},
        ).status_code
        == 422
    )
    db.expire_all()
    after = db.scalar(
        select(func.count()).select_from(Delivery).where(Delivery.innings_id == innings.id)
    )
    assert before == after


def test_service_resolve_and_uuid(
    started_five_overs: tuple[Match, Innings, SeededSides],
    db: Session,
) -> None:
    _, innings, sides = started_five_overs
    result = submit_delivery(
        db,
        innings.id,
        DeliveryCreateRequest(
            striker_id=sides.striker.id,
            non_striker_id=sides.non_striker.id,
            bowler_id=sides.bowler.id,
            delivery_type=DeliveryType.NO_BALL,
            bat_runs=6,
        ),
    )
    assert result.total_runs == 7
    assert result.is_legal is False
    assert result.id.version == 7
    assert result.delivery_type is DeliveryType.NO_BALL
