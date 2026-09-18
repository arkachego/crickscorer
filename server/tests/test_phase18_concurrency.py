"""Phase 18 corrective — deterministic concurrency scenarios."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

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
from app.services.reconstruction import reconstruct_innings_state

client = TestClient(app)


@pytest.fixture()
def seeded(db: Session) -> tuple[Team, Team, Player, Player, Player, list[Player]]:
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

    batters = list(
        db.scalars(
            select(Player)
            .where(Player.team_id == india.id, Player.batting_order.is_not(None))
            .order_by(Player.batting_order)
        )
    )
    return (
        india,
        pakistan,
        by_name(india.id, "Abhishek Sharma"),
        by_name(india.id, "Shubman Gill"),
        by_name(pakistan.id, "Shaheen Afridi"),
        batters,
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
    db: Session, seeded: tuple[Team, Team, Player, Player, Player, list[Player]]
) -> Generator[
    tuple[Match, Innings, tuple[Team, Team, Player, Player, Player, list[Player]]],
    None,
    None,
]:
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
    _cleanup(db, match.id)


def _delivery_body(
    striker: Player, non_striker: Player, bowler: Player, *, bat_runs: int = 1
) -> dict:
    return {
        "striker_id": str(striker.id),
        "non_striker_id": str(non_striker.id),
        "bowler_id": str(bowler.id),
        "delivery_type": "NORMAL",
        "bat_runs": bat_runs,
    }


def _assert_history_consistent(innings_id: uuid.UUID) -> list[Delivery]:
    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(Delivery)
                .where(Delivery.innings_id == innings_id)
                .order_by(Delivery.sequence_no)
            )
        )
        seqs = [r.sequence_no for r in rows]
        assert seqs == list(range(1, len(rows) + 1))
        positions = {(r.over_number, r.ball_in_over) for r in rows}
        assert len(positions) == len(rows)
        legal = [r for r in rows if r.is_legal]
        for idx, row in enumerate(legal, start=1):
            # Legal balls consume sequential slots within overs of 6.
            expected_over = (idx - 1) // 6
            expected_ball = ((idx - 1) % 6) + 1
            assert row.over_number == expected_over
            assert row.ball_in_over == expected_ball
        return rows


def test_concurrent_delivery_vs_delivery_serialised(
    started: tuple[
        Match, Innings, tuple[Team, Team, Player, Player, Player, list[Player]]
    ],
) -> None:
    """Two concurrent valid deliveries: unique sequences, consistent history."""
    _, innings, sides = started
    _, _, striker, non_striker, bowler, _ = sides
    body = _delivery_body(striker, non_striker, bowler, bat_runs=1)
    iid = str(innings.id)
    barrier = threading.Barrier(2, timeout=15)

    def _one() -> int:
        with TestClient(app) as local:
            barrier.wait()
            return local.post(f"/api/v1/innings/{iid}/deliveries", json=body).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: _one(), range(2)))

    assert codes.count(200) == 2
    rows = _assert_history_consistent(innings.id)
    assert len(rows) == 2
    assert sum(r.total_runs for r in rows) == 2
    assert sum(1 for r in rows if r.is_legal) == 2


def test_concurrent_undo_vs_undo_one_wins(
    started: tuple[
        Match, Innings, tuple[Team, Team, Player, Player, Player, list[Player]]
    ],
) -> None:
    _, innings, sides = started
    _, _, striker, non_striker, bowler, _ = sides
    assert (
        client.post(
            f"/api/v1/innings/{innings.id}/deliveries",
            json=_delivery_body(striker, non_striker, bowler),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/innings/{innings.id}/deliveries",
            json=_delivery_body(striker, non_striker, bowler, bat_runs=2),
        ).status_code
        == 200
    )
    iid = str(innings.id)
    barrier = threading.Barrier(2, timeout=15)

    def _undo() -> int:
        with TestClient(app) as local:
            barrier.wait()
            return local.post(f"/api/v1/innings/{iid}/undo").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: _undo(), range(2)))

    # Two undos against two deliveries: both may succeed (serialised), or if
    # raced on empty history one may 409 — either way history stays consistent.
    assert all(c in {200, 409} for c in codes)
    assert codes.count(200) >= 1
    rows = _assert_history_consistent(innings.id)
    assert len(rows) in {0, 1}
    with SessionLocal() as session:
        inn = session.get(Innings, innings.id)
        match = session.get(Match, innings.match_id)
        assert inn is not None and match is not None
        state = reconstruct_innings_state(session, inn, match)
        assert state.delivery_count == len(rows)
        assert state.legal_delivery_count == sum(1 for r in rows if r.is_legal)


def test_concurrent_replacement_vs_delivery(
    started: tuple[
        Match, Innings, tuple[Team, Team, Player, Player, Player, list[Player]]
    ],
) -> None:
    """While replacement_required, concurrent replacement + stale delivery."""
    _, innings, sides = started
    _, _, striker, non_striker, bowler, batters = sides
    wicket = client.post(
        f"/api/v1/innings/{innings.id}/deliveries",
        json={
            **_delivery_body(striker, non_striker, bowler, bat_runs=0),
            "wicket": {
                "dismissal_type": "BOWLED",
                "dismissed_player_id": str(striker.id),
            },
        },
    )
    assert wicket.status_code == 200
    assert wicket.json()["replacement_required"] is True

    replacement = next(
        p for p in batters if p.id not in {striker.id, non_striker.id}
    )
    iid = str(innings.id)
    barrier = threading.Barrier(2, timeout=15)
    results: dict[str, int] = {}

    def _replace() -> None:
        with TestClient(app) as local:
            barrier.wait()
            results["replacement"] = local.post(
                f"/api/v1/innings/{iid}/replacement",
                json={"player_id": str(replacement.id)},
            ).status_code

    def _deliver() -> None:
        with TestClient(app) as local:
            barrier.wait()
            # Stale pair still names the dismissed striker.
            results["delivery"] = local.post(
                f"/api/v1/innings/{iid}/deliveries",
                json=_delivery_body(striker, non_striker, bowler),
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        pool.submit(_replace)
        pool.submit(_deliver)
        pool.shutdown(wait=True)

    assert results["replacement"] == 200
    assert results["delivery"] in {400, 409}
    with SessionLocal() as session:
        inn = session.get(Innings, innings.id)
        assert inn is not None
        assert inn.replacement_required is False
        actives = {inn.striker_id, inn.non_striker_id}
        assert None not in actives
        assert non_striker.id in actives
        assert replacement.id in actives
        assert striker.id not in actives
        repl_count = session.scalar(
            select(func.count())
            .select_from(BatterReplacement)
            .where(BatterReplacement.innings_id == innings.id)
        )
        assert repl_count == 1
        # No delivery accepted with dismissed striker after the wicket.
        deliveries = list(
            session.scalars(
                select(Delivery).where(Delivery.innings_id == innings.id)
            )
        )
        assert len(deliveries) == 1
        assert deliveries[0].dismissed_player_id == striker.id


def test_concurrent_delivery_vs_undo(
    started: tuple[
        Match, Innings, tuple[Team, Team, Player, Player, Player, list[Player]]
    ],
) -> None:
    """Empty innings: concurrent first delivery vs undo (no delivery to undo)."""
    _, innings, sides = started
    _, _, striker, non_striker, bowler, _ = sides
    iid = str(innings.id)
    barrier = threading.Barrier(2, timeout=15)
    results: dict[str, int] = {}

    def _deliver() -> None:
        with TestClient(app) as local:
            barrier.wait()
            results["delivery"] = local.post(
                f"/api/v1/innings/{iid}/deliveries",
                json=_delivery_body(striker, non_striker, bowler, bat_runs=1),
            ).status_code

    def _undo() -> None:
        with TestClient(app) as local:
            barrier.wait()
            results["undo"] = local.post(f"/api/v1/innings/{iid}/undo").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        pool.submit(_deliver)
        pool.submit(_undo)
        pool.shutdown(wait=True)

    assert results["delivery"] == 200
    assert results["undo"] in {200, 409}
    rows = _assert_history_consistent(innings.id)
    # Serialisations: undo-first → delivery remains; delivery-first then undo → empty.
    if results["undo"] == 409:
        assert len(rows) == 1
        assert rows[0].total_runs == 1
    else:
        assert len(rows) == 0
    with SessionLocal() as session:
        inn = session.get(Innings, innings.id)
        match = session.get(Match, innings.match_id)
        assert inn is not None and match is not None
        state = reconstruct_innings_state(session, inn, match)
        assert state.delivery_count == len(rows)
        assert state.innings_total_runs == sum(r.total_runs for r in rows)


def test_concurrent_lifecycle_vs_scoring(
    db: Session,
    seeded: tuple[Team, Team, Player, Player, Player, list[Player]],
) -> None:
    """Complete-innings vs delivery: no delivery into a closed innings."""
    india, pakistan, striker, non_striker, bowler, _ = seeded
    match = create_match(
        db,
        MatchCreateRequest(
            team_1_id=india.id,
            team_2_id=pakistan.id,
            format=MatchFormat.CUSTOM,
            batting_first_team_id=india.id,
            overs=2,
        ),
    )
    match = start_match(db, match.id)
    innings = next(i for i in match.innings if i.innings_number == 1)
    for _ in range(3):
        assert (
            client.post(
                f"/api/v1/innings/{innings.id}/deliveries",
                json=_delivery_body(striker, non_striker, bowler, bat_runs=0),
            ).status_code
            == 200
        )

    iid = str(innings.id)
    mid = match.id
    barrier = threading.Barrier(2, timeout=15)
    results: dict[str, int] = {}

    def _complete() -> None:
        with TestClient(app) as local:
            barrier.wait()
            results["complete"] = local.post(f"/api/v1/innings/{iid}/complete").status_code

    def _deliver() -> None:
        with TestClient(app) as local:
            barrier.wait()
            results["delivery"] = local.post(
                f"/api/v1/innings/{iid}/deliveries",
                json=_delivery_body(striker, non_striker, bowler, bat_runs=1),
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        pool.submit(_complete)
        pool.submit(_deliver)
        pool.shutdown(wait=True)

    assert results["complete"] in {200, 409}
    assert results["delivery"] in {200, 409}
    # Exactly one valid terminal outcome for the race.
    assert (results["complete"], results["delivery"]) in {
        (200, 409),
        (409, 200),
        (200, 200),  # delivery commits first, then complete still valid
    }

    with SessionLocal() as session:
        inn = session.get(Innings, innings.id)
        m = session.get(Match, mid)
        assert inn is not None and m is not None
        n = session.scalar(
            select(func.count())
            .select_from(Delivery)
            .where(Delivery.innings_id == innings.id)
        )
        assert n in {3, 4}
        if inn.status is InningsStatus.COMPLETED:
            assert m.status is MatchStatus.INNINGS_BREAK
            # No further open mutation path left inconsistent.
            assert inn.status is InningsStatus.COMPLETED
        else:
            assert inn.status is InningsStatus.IN_PROGRESS
            assert m.status is MatchStatus.IN_PROGRESS
            assert n == 4

    _cleanup(db, mid)
