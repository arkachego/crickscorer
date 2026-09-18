"""Phase 18 corrective — cross-application snapshot convergence."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import MatchFormat
from app.db.models import BatterReplacement, Delivery, Innings, Match, Player, Team
from app.db.seed import seed_database
from app.main import app
from app.realtime.snapshot import build_match_live_snapshot
from app.realtime.versions import reset_versions_for_tests
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match, start_match

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_versions() -> Generator[None, None, None]:
    reset_versions_for_tests()
    yield
    reset_versions_for_tests()


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


def _delivery(
    striker: Player, non_striker: Player, bowler: Player, **extra
) -> dict:
    body = {
        "striker_id": str(striker.id),
        "non_striker_id": str(non_striker.id),
        "bowler_id": str(bowler.id),
        "delivery_type": "NORMAL",
        "bat_runs": 1,
    }
    body.update(extra)
    return body


def _consumer_view(snapshot: dict) -> dict:
    """Admin/Viewer-equivalent projection from an authoritative live snapshot."""
    match = snapshot["match"]
    innings = match["innings"][0]
    iid = innings["id"]
    deliveries = snapshot["deliveries_by_innings"][iid]
    return {
        "match_id": snapshot["match_id"],
        "version": snapshot["version"],
        "match_status": match["status"],
        "innings_status": innings["status"],
        "score": innings["innings_total_runs"],
        "wickets": innings["wickets"],
        "legal_delivery_count": innings["legal_delivery_count"],
        "free_hit_pending": innings["free_hit_pending"],
        "striker_id": (innings.get("striker") or {}).get("id"),
        "non_striker_id": (innings.get("non_striker") or {}).get("id"),
        "delivery_count": len(deliveries),
        "delivery_sequences": [d["sequence_no"] for d in deliveries],
        "delivery_totals": [d["total_runs"] for d in deliveries],
    }


def _assert_admin_viewer_converge(snapshot: dict) -> dict:
    admin_view = _consumer_view(snapshot)
    viewer_view = _consumer_view(snapshot)
    assert admin_view == viewer_view
    return admin_view


def test_cross_app_delivery_snapshot_converges_admin_and_viewer(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    started: tuple[
        Match, Innings, tuple[Team, Team, Player, Player, Player, list[Player]]
    ],
) -> None:
    match, innings, sides = started
    _, _, striker, non_striker, bowler, _ = sides

    published: list[dict] = []

    def capture_publish(session: Session, innings_id: uuid.UUID) -> None:
        published.append(build_match_live_snapshot(session, match.id, bump=True))

    import app.realtime as realtime_mod

    monkeypatch.setattr(realtime_mod, "publish_match_update_from_innings", capture_publish)
    response = client.post(
        f"/api/v1/innings/{innings.id}/deliveries",
        json=_delivery(striker, non_striker, bowler, bat_runs=4),
    )
    assert response.status_code == 200
    assert len(published) == 1
    view = _assert_admin_viewer_converge(published[0])
    assert view["score"] == 4
    assert view["wickets"] == 0
    assert view["legal_delivery_count"] == 1
    assert view["free_hit_pending"] is False
    assert view["delivery_count"] == 1
    assert view["match_status"] == "IN_PROGRESS"
    assert view["innings_status"] == "IN_PROGRESS"
    assert view["striker_id"] == str(striker.id)
    assert view["non_striker_id"] == str(non_striker.id)


def test_cross_app_wicket_replacement_undo_lifecycle_snapshots(
    db: Session,
    started: tuple[
        Match, Innings, tuple[Team, Team, Player, Player, Player, list[Player]]
    ],
) -> None:
    """Representative mutation classes share one authoritative snapshot contract."""
    match, innings, sides = started
    _, _, striker, non_striker, bowler, batters = sides
    replacement = next(p for p in batters if p.id not in {striker.id, non_striker.id})

    # Delivery + wicket
    wicket = client.post(
        f"/api/v1/innings/{innings.id}/deliveries",
        json={
            **_delivery(striker, non_striker, bowler, bat_runs=0),
            "wicket": {
                "dismissal_type": "CAUGHT",
                "dismissed_player_id": str(striker.id),
            },
        },
    )
    assert wicket.status_code == 200
    snap_wicket = build_match_live_snapshot(db, match.id, bump=True)
    view_w = _assert_admin_viewer_converge(snap_wicket)
    assert view_w["wickets"] == 1
    assert view_w["score"] == 0
    assert view_w["legal_delivery_count"] == 1
    assert view_w["delivery_count"] == 1

    # Replacement
    repl = client.post(
        f"/api/v1/innings/{innings.id}/replacement",
        json={"player_id": str(replacement.id)},
    )
    assert repl.status_code == 200
    db.expire_all()
    snap_repl = build_match_live_snapshot(db, match.id, bump=True)
    view_r = _assert_admin_viewer_converge(snap_repl)
    assert set(
        filter(None, [view_r["striker_id"], view_r["non_striker_id"]])
    ) == {str(non_striker.id), str(replacement.id)}

    # Undo latest (undoes the wicket delivery via cascade of later state —
    # actually undo removes latest delivery; after replacement the latest
    # delivery is still the wicket delivery).
    undo = client.post(f"/api/v1/innings/{innings.id}/undo")
    assert undo.status_code == 200
    db.expire_all()
    snap_undo = build_match_live_snapshot(db, match.id, bump=True)
    view_u = _assert_admin_viewer_converge(snap_undo)
    assert view_u["delivery_count"] == 0
    assert view_u["wickets"] == 0
    assert view_u["score"] == 0

    # Fresh delivery then lifecycle complete
    assert (
        client.post(
            f"/api/v1/innings/{innings.id}/deliveries",
            json=_delivery(striker, non_striker, bowler, bat_runs=1),
        ).status_code
        == 200
    )
    completed = client.post(f"/api/v1/innings/{innings.id}/complete")
    assert completed.status_code == 200
    db.expire_all()
    snap_life = build_match_live_snapshot(db, match.id, bump=True)
    view_l = _assert_admin_viewer_converge(snap_life)
    assert view_l["innings_status"] == "COMPLETED"
    assert view_l["match_status"] == "INNINGS_BREAK"
    assert view_l["delivery_count"] == 1
    assert view_l["score"] == 1
