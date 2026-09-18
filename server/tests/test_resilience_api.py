"""Phase 16 — error handling and resilience tests."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import MatchFormat
from app.db.models import Delivery, Innings, Match, Player, Team
from app.db.seed import seed_database
from app.main import app, fastapi_app
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match, start_match

client = TestClient(app)


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


def test_health_unchanged() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Request-ID" in response.headers


def test_http_cors_allowlist_for_admin_origin() -> None:
    """HTTP CORS mirrors Socket.IO allowlist for local Admin/Viewer origins."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

    denied = client.get("/health", headers={"Origin": "http://evil.example"})
    assert denied.status_code == 200
    assert denied.headers.get("access-control-allow-origin") is None


def test_request_id_propagated_and_generated() -> None:
    custom = "phase16-correlation-id"
    response = client.get("/health", headers={"X-Request-ID": custom})
    assert response.headers["X-Request-ID"] == custom

    generated = client.get("/health")
    assert generated.headers["X-Request-ID"]
    assert generated.headers["X-Request-ID"] != custom


def test_not_found_keeps_structured_contract() -> None:
    response = client.get(f"/api/v1/matches/{uuid.uuid4()}")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["code"] == "MATCH_NOT_FOUND"
    assert "message" in body["detail"]


def test_conflict_keeps_structured_contract(
    db: Session,
    started: tuple[Match, Innings, tuple[Team, Team, Player, Player, Player]],
) -> None:
    _, innings, sides = started
    _, _, striker, _non_striker, bowler = sides
    response = client.post(
        f"/api/v1/innings/{innings.id}/deliveries",
        json={
            "striker_id": str(striker.id),
            "non_striker_id": str(striker.id),
            "bowler_id": str(bowler.id),
            "delivery_type": "NORMAL",
            "bat_runs": 1,
        },
    )
    assert response.status_code in {400, 409}
    detail = response.json()["detail"]
    assert "code" in detail
    assert "message" in detail
    assert "IntegrityError" not in detail["message"]
    assert "Traceback" not in detail["message"]


def test_unhandled_exception_returns_safe_500() -> None:
    async def boom():
        raise RuntimeError("secret internal detail")

    fastapi_app.add_api_route("/__phase16_boom", boom, methods=["GET"])
    # raise_server_exceptions=False so we assert the handled JSON response.
    local = TestClient(app, raise_server_exceptions=False)
    try:
        response = local.get("/__phase16_boom")
        assert response.status_code == 500
        detail = response.json()["detail"]
        assert detail["code"] == "INTERNAL_SERVER_ERROR"
        assert "secret" not in detail["message"].lower()
        assert "Traceback" not in str(response.json())
    finally:
        fastapi_app.router.routes = [
            route
            for route in fastapi_app.router.routes
            if getattr(route, "path", None) != "/__phase16_boom"
        ]


def test_publish_failure_does_not_fail_committed_delivery(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    started: tuple[Match, Innings, tuple[Team, Team, Player, Player, Player]],
) -> None:
    _, innings, sides = started
    _, _, striker, non_striker, bowler = sides

    def explode(*_a, **_k):
        raise RuntimeError("socket down")

    # Patch the inner publisher; package wrapper must swallow the error.
    monkeypatch.setattr(
        "app.realtime._publish_match_update_from_innings",
        explode,
    )

    response = client.post(
        f"/api/v1/innings/{innings.id}/deliveries",
        json={
            "striker_id": str(striker.id),
            "non_striker_id": str(non_striker.id),
            "bowler_id": str(bowler.id),
            "delivery_type": "NORMAL",
            "bat_runs": 2,
        },
    )
    assert response.status_code == 200, response.text
    n = db.scalar(
        select(func.count()).select_from(Delivery).where(Delivery.innings_id == innings.id)
    )
    assert n == 1


def test_socket_publish_exception_swallowed(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    started: tuple[Match, Innings, tuple[Team, Team, Player, Player, Player]],
) -> None:
    match, _, _ = started
    from app.realtime.socket import publish_match_update

    monkeypatch.setattr(
        "app.realtime.socket.build_match_live_snapshot",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    publish_match_update(match.id)
