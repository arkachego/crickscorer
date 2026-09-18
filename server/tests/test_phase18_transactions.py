"""Phase 18 corrective — forced pre-commit transaction rollback."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from unittest.mock import MagicMock

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

# raise_server_exceptions=False so forced commit failures surface as HTTP 500.
client = TestClient(app, raise_server_exceptions=False)


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


def _delivery_json(
    striker: Player, non_striker: Player, bowler: Player, *, bat_runs: int = 1
) -> dict:
    return {
        "striker_id": str(striker.id),
        "non_striker_id": str(non_striker.id),
        "bowler_id": str(bowler.id),
        "delivery_type": "NORMAL",
        "bat_runs": bat_runs,
    }


def _force_commit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raise after mutation work has begun, before the transaction commits."""

    def boom(self) -> None:  # noqa: ANN001
        raise RuntimeError("forced pre-commit failure")

    monkeypatch.setattr(Session, "commit", boom)


def _restore_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo patches before fixture cleanup commits."""
    monkeypatch.undo()


def _spy_publish(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    spy = MagicMock()
    monkeypatch.setattr("app.realtime.publish_match_update", spy)
    monkeypatch.setattr("app.realtime.publish_match_update_from_innings", spy)
    return spy


def test_delivery_forced_commit_rolls_back_and_does_not_publish(
    monkeypatch: pytest.MonkeyPatch,
    started: tuple[
        Match, Innings, tuple[Team, Team, Player, Player, Player, list[Player]]
    ],
) -> None:
    match, innings, sides = started
    _, _, striker, non_striker, bowler, _ = sides
    publish = _spy_publish(monkeypatch)
    _force_commit_failure(monkeypatch)

    try:
        response = client.post(
            f"/api/v1/innings/{innings.id}/deliveries",
            json=_delivery_json(striker, non_striker, bowler, bat_runs=3),
        )
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == "INTERNAL_SERVER_ERROR"
        publish.assert_not_called()

        with SessionLocal() as session:
            n = session.scalar(
                select(func.count())
                .select_from(Delivery)
                .where(Delivery.innings_id == innings.id)
            )
            assert n == 0
            inn = session.get(Innings, innings.id)
            m = session.get(Match, match.id)
            assert inn is not None and m is not None
            assert inn.status is InningsStatus.IN_PROGRESS
            assert m.status is MatchStatus.IN_PROGRESS
            state = reconstruct_innings_state(session, inn, m)
            assert state.delivery_count == 0
            assert state.legal_delivery_count == 0
            assert state.innings_total_runs == 0
    finally:
        _restore_commit(monkeypatch)


def test_replacement_forced_commit_rolls_back_and_does_not_publish(
    monkeypatch: pytest.MonkeyPatch,
    started: tuple[
        Match, Innings, tuple[Team, Team, Player, Player, Player, list[Player]]
    ],
) -> None:
    match, innings, sides = started
    _, _, striker, non_striker, bowler, batters = sides
    wicket = client.post(
        f"/api/v1/innings/{innings.id}/deliveries",
        json={
            **_delivery_json(striker, non_striker, bowler, bat_runs=0),
            "wicket": {
                "dismissal_type": "BOWLED",
                "dismissed_player_id": str(striker.id),
            },
        },
    )
    assert wicket.status_code == 200

    with SessionLocal() as session:
        before = session.get(Innings, innings.id)
        assert before is not None
        assert before.replacement_required is True
        before_striker = before.striker_id
        before_non = before.non_striker_id

    replacement = next(p for p in batters if p.id not in {striker.id, non_striker.id})
    publish = _spy_publish(monkeypatch)
    _force_commit_failure(monkeypatch)

    try:
        response = client.post(
            f"/api/v1/innings/{innings.id}/replacement",
            json={"player_id": str(replacement.id)},
        )
        assert response.status_code == 500
        publish.assert_not_called()

        with SessionLocal() as session:
            inn = session.get(Innings, innings.id)
            assert inn is not None
            assert inn.replacement_required is True
            assert inn.striker_id == before_striker
            assert inn.non_striker_id == before_non
            repl_n = session.scalar(
                select(func.count())
                .select_from(BatterReplacement)
                .where(BatterReplacement.innings_id == innings.id)
            )
            assert repl_n == 0
            assert session.get(Match, match.id).status is MatchStatus.IN_PROGRESS
    finally:
        _restore_commit(monkeypatch)


def test_undo_forced_commit_rolls_back_wicket_replacement_and_does_not_publish(
    monkeypatch: pytest.MonkeyPatch,
    started: tuple[
        Match, Innings, tuple[Team, Team, Player, Player, Player, list[Player]]
    ],
) -> None:
    match, innings, sides = started
    _, _, striker, non_striker, bowler, batters = sides
    assert (
        client.post(
            f"/api/v1/innings/{innings.id}/deliveries",
            json={
                **_delivery_json(striker, non_striker, bowler, bat_runs=0),
                "wicket": {
                    "dismissal_type": "BOWLED",
                    "dismissed_player_id": str(striker.id),
                },
            },
        ).status_code
        == 200
    )
    replacement = next(p for p in batters if p.id not in {striker.id, non_striker.id})
    assert (
        client.post(
            f"/api/v1/innings/{innings.id}/replacement",
            json={"player_id": str(replacement.id)},
        ).status_code
        == 200
    )

    with SessionLocal() as session:
        before_deliveries = session.scalar(
            select(func.count())
            .select_from(Delivery)
            .where(Delivery.innings_id == innings.id)
        )
        before_repl = session.scalar(
            select(func.count())
            .select_from(BatterReplacement)
            .where(BatterReplacement.innings_id == innings.id)
        )
        inn_before = session.get(Innings, innings.id)
        assert inn_before is not None
        before_required = inn_before.replacement_required
        before_pair = (inn_before.striker_id, inn_before.non_striker_id)

    publish = _spy_publish(monkeypatch)
    _force_commit_failure(monkeypatch)

    try:
        response = client.post(f"/api/v1/innings/{innings.id}/undo")
        assert response.status_code == 500
        publish.assert_not_called()

        with SessionLocal() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Delivery)
                    .where(Delivery.innings_id == innings.id)
                )
                == before_deliveries
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(BatterReplacement)
                    .where(BatterReplacement.innings_id == innings.id)
                )
                == before_repl
            )
            inn = session.get(Innings, innings.id)
            m = session.get(Match, match.id)
            assert inn is not None and m is not None
            assert inn.replacement_required == before_required
            assert (inn.striker_id, inn.non_striker_id) == before_pair
            assert m.status is MatchStatus.IN_PROGRESS
            state = reconstruct_innings_state(session, inn, m)
            assert state.delivery_count == before_deliveries
    finally:
        _restore_commit(monkeypatch)


def test_lifecycle_forced_commit_rolls_back_and_does_not_publish(
    monkeypatch: pytest.MonkeyPatch,
    started: tuple[
        Match, Innings, tuple[Team, Team, Player, Player, Player, list[Player]]
    ],
) -> None:
    match, innings, sides = started
    _, _, striker, non_striker, bowler, _ = sides
    assert (
        client.post(
            f"/api/v1/innings/{innings.id}/deliveries",
            json=_delivery_json(striker, non_striker, bowler, bat_runs=0),
        ).status_code
        == 200
    )

    publish = _spy_publish(monkeypatch)
    _force_commit_failure(monkeypatch)

    try:
        response = client.post(f"/api/v1/innings/{innings.id}/complete")
        assert response.status_code == 500
        publish.assert_not_called()

        with SessionLocal() as session:
            inn = session.get(Innings, innings.id)
            m = session.get(Match, match.id)
            assert inn is not None and m is not None
            assert inn.status is InningsStatus.IN_PROGRESS
            assert m.status is MatchStatus.IN_PROGRESS
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Delivery)
                    .where(Delivery.innings_id == innings.id)
                )
                == 1
            )
    finally:
        _restore_commit(monkeypatch)
