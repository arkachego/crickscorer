"""Core scoring engine API and service tests (Phase 9)."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.db.enums import InningsStatus, MatchFormat, MatchStatus
from app.db.models import Delivery, Innings, Match, Player, Team
from app.db.seed import seed_database
from app.db.session import SessionLocal
from app.main import app
from app.schemas.delivery import DeliveryCreateRequest
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match, start_match, start_next_innings
from app.services.scoring import (
    max_legal_deliveries,
    next_delivery_position,
    submit_delivery,
)

client = TestClient(app)
MATCHES_URL = "/api/v1/matches"


@dataclass(frozen=True)
class SeededSides:
    india: Team
    pakistan: Team
    striker: Player  # Abhishek Sharma
    non_striker: Player  # Shubman Gill
    bowler: Player  # Shaheen Afridi
    india_bowler_only: Player  # Jasprit Bumrah
    pakistan_batter: Player  # Fakhar Zaman
    india_coach: Player  # Gautam Gambhir
    pakistan_coach: Player  # Mike Hesson


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
        india_bowler_only=by_name(india.id, "Jasprit Bumrah"),
        pakistan_batter=by_name(pakistan.id, "Fakhar Zaman"),
        india_coach=by_name(india.id, "Gautam Gambhir"),
        pakistan_coach=by_name(pakistan.id, "Mike Hesson"),
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
def started_custom(
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


def _payload(
    sides: SeededSides,
    bat_runs: int,
    *,
    striker: Player | None = None,
    non_striker: Player | None = None,
    bowler: Player | None = None,
) -> dict[str, object]:
    return {
        "striker_id": str((striker or sides.striker).id),
        "non_striker_id": str((non_striker or sides.non_striker).id),
        "bowler_id": str((bowler or sides.bowler).id),
        "bat_runs": bat_runs,
    }


def _post_delivery(innings_id: uuid.UUID, body: dict[str, object]):
    return client.post(f"/api/v1/innings/{innings_id}/deliveries", json=body)


# --- Position helpers ---


def test_next_delivery_position_and_max_legal() -> None:
    assert next_delivery_position(delivery_count=0, legal_count=0) == (1, 0, 1)
    assert next_delivery_position(delivery_count=5, legal_count=5) == (6, 0, 6)
    assert next_delivery_position(delivery_count=6, legal_count=6) == (7, 1, 1)
    # Illegal deliveries increase sequence without consuming legal balls.
    assert next_delivery_position(delivery_count=3, legal_count=2) == (4, 0, 3)
    assert max_legal_deliveries(10) == 60
    assert max_legal_deliveries(20) == 120
    assert max_legal_deliveries(50) == 300
    assert max_legal_deliveries(5) == 30


# --- Basic delivery + progression + score ---


@pytest.mark.parametrize("bat_runs", [0, 1, 2, 3, 4, 6])
def test_legal_bat_runs_persist(
    started_custom: tuple[Match, Innings, SeededSides],
    db: Session,
    bat_runs: int,
) -> None:
    _, innings, sides = started_custom
    # Isolate each bat_runs on a fresh innings via unique match — fixture is per test.
    response = _post_delivery(innings.id, _payload(sides, bat_runs))
    assert response.status_code == 200
    data = response.json()
    assert data["bat_runs"] == bat_runs
    assert data["total_runs"] == bat_runs
    assert data["is_legal"] is True
    assert data["sequence_no"] == 1
    assert data["over_number"] == 0
    assert data["ball_in_over"] == 1
    assert data["innings_total_runs"] == bat_runs
    assert uuid.UUID(data["id"]).version == 7

    row = db.execute(
        text(
            "SELECT uuid_extract_version(id), total_runs, is_legal, "
            "wide_runs, no_ball_runs, bye_runs, leg_bye_runs, dismissal_type "
            "FROM deliveries WHERE id = :id"
        ),
        {"id": uuid.UUID(data["id"])},
    ).one()
    assert row[0] == 7
    assert row[1] == bat_runs
    assert row[2] is True
    assert row[3:] == (0, 0, 0, 0, None)


def test_ball_progression_and_score_sequence(
    started_custom: tuple[Match, Innings, SeededSides],
    db: Session,
) -> None:
    _, innings, sides = started_custom
    sequence = [1, 2, 4, 0, 6, 3, 1]
    expected_positions = [
        (1, 0, 1),
        (2, 0, 2),
        (3, 0, 3),
        (4, 0, 4),
        (5, 0, 5),
        (6, 0, 6),
        (7, 1, 1),
    ]
    for runs, (seq, over, ball) in zip(sequence, expected_positions, strict=True):
        data = _post_delivery(innings.id, _payload(sides, runs)).json()
        assert data["sequence_no"] == seq
        assert data["over_number"] == over
        assert data["ball_in_over"] == ball

    assert sum(sequence) == 17
    last = _post_delivery(innings.id, _payload(sides, 0)).json()
    assert last["innings_total_runs"] == 17
    assert last["sequence_no"] == 8
    assert last["over_number"] == 1
    assert last["ball_in_over"] == 2

    ordered = list(
        db.scalars(
            select(Delivery)
            .where(Delivery.innings_id == innings.id)
            .order_by(Delivery.over_number, Delivery.ball_in_over, Delivery.id)
        )
    )
    assert [d.sequence_no for d in ordered] == list(range(1, 9))


def test_invalid_bat_runs_rejected(
    started_custom: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started_custom
    for bad in (5, 7, -1, 8):
        response = _post_delivery(innings.id, _payload(sides, bad))
        assert response.status_code == 422


# --- Configured overs completion (service-level for large formats) ---


def _submit_n(
    session: Session,
    innings_id: uuid.UUID,
    sides: SeededSides,
    n: int,
):
    last = None
    for _ in range(n):
        last = submit_delivery(
            session,
            innings_id,
            DeliveryCreateRequest(
                striker_id=sides.striker.id,
                non_striker_id=sides.non_striker.id,
                bowler_id=sides.bowler.id,
                bat_runs=0,
            ),
        )
    return last


def test_format_completion_limits(db: Session, seeded: SeededSides) -> None:
    cases = [
        (MatchFormat.T10, None, 60),
        (MatchFormat.T20, None, 120),
        (MatchFormat.ONE_DAY, None, 300),
        (MatchFormat.CUSTOM, 5, 30),
    ]
    for fmt, overs, expected_max in cases:
        assert max_legal_deliveries(overs or {MatchFormat.T10: 10, MatchFormat.T20: 20, MatchFormat.ONE_DAY: 50}[fmt]) == expected_max
        match = create_match(
            db,
            MatchCreateRequest(
                team_1_id=seeded.india.id,
                team_2_id=seeded.pakistan.id,
                format=fmt,
                batting_first_team_id=seeded.india.id,
                overs=overs,
            ),
        )
        match = start_match(db, match.id)
        innings_id = match.innings[0].id
        # Submit all but one via service, then final via API for at least CUSTOM.
        n = expected_max
        last = _submit_n(db, innings_id, seeded, n)
        assert last is not None
        assert last.innings_status is InningsStatus.COMPLETED
        assert last.match_status is MatchStatus.INNINGS_BREAK
        assert last.sequence_no == n
        count = db.scalar(
            select(func.count()).select_from(Delivery).where(Delivery.innings_id == innings_id)
        )
        assert count == n
        # Reject further delivery.
        blocked = _post_delivery(innings_id, _payload(seeded, 1))
        assert blocked.status_code == 409
        _cleanup_match(db, match.id)


def test_custom_one_over_api_completion_both_innings(
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
    innings_1 = match.innings[0].id

    for i in range(5):
        assert _post_delivery(innings_1, _payload(seeded, 1)).status_code == 200

    final_1 = _post_delivery(innings_1, _payload(seeded, 4))
    assert final_1.status_code == 200
    body = final_1.json()
    assert body["innings_status"] == InningsStatus.COMPLETED.value
    assert body["match_status"] == MatchStatus.INNINGS_BREAK.value
    assert body["innings_total_runs"] == 9
    assert _post_delivery(innings_1, _payload(seeded, 0)).status_code == 409

    started_2 = client.post(f"{MATCHES_URL}/{match.id}/innings/start")
    assert started_2.status_code == 200
    innings_2 = next(
        i for i in started_2.json()["innings"] if i["innings_number"] == 2
    )
    # Pakistan batting: swap sides for participants.
    pak_payload = {
        "striker_id": str(seeded.pakistan_batter.id),
        "non_striker_id": str(
            db.scalar(
                select(Player).where(
                    Player.team_id == seeded.pakistan.id,
                    Player.name == "Saim Ayub",
                )
            ).id
        ),
        "bowler_id": str(seeded.india_bowler_only.id),
        "bat_runs": 0,
    }
    for _ in range(5):
        assert _post_delivery(uuid.UUID(innings_2["id"]), pak_payload).status_code == 200
    final_2 = _post_delivery(uuid.UUID(innings_2["id"]), {**pak_payload, "bat_runs": 1})
    assert final_2.status_code == 200
    done = final_2.json()
    assert done["innings_status"] == InningsStatus.COMPLETED.value
    assert done["match_status"] == MatchStatus.COMPLETED.value
    assert _post_delivery(uuid.UUID(innings_2["id"]), pak_payload).status_code == 409

    _cleanup_match(db, match.id)


# --- Participant validation ---


def test_participant_validation(
    started_custom: tuple[Match, Innings, SeededSides],
    db: Session,
) -> None:
    _, innings, sides = started_custom

    ok = _post_delivery(innings.id, _payload(sides, 1))
    assert ok.status_code == 200

    # Wrong teams
    assert (
        _post_delivery(
            innings.id,
            _payload(sides, 0, striker=sides.pakistan_batter),
        ).status_code
        == 400
    )
    assert (
        _post_delivery(
            innings.id,
            _payload(sides, 0, non_striker=sides.pakistan_batter),
        ).status_code
        == 400
    )
    assert (
        _post_delivery(
            innings.id,
            _payload(sides, 0, bowler=sides.india_bowler_only),
        ).status_code
        == 400
    )

    # Same player
    same = _post_delivery(
        innings.id,
        _payload(sides, 0, non_striker=sides.striker),
    )
    assert same.status_code == 400
    assert same.json()["detail"]["code"] == "STRIKER_EQUALS_NON_STRIKER"

    # Coaches
    for field, player in (
        ("striker", sides.india_coach),
        ("non_striker", sides.india_coach),
        ("bowler", sides.pakistan_coach),
    ):
        kwargs = {field: player}
        resp = _post_delivery(innings.id, _payload(sides, 0, **kwargs))
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "COACH_NOT_ALLOWED"

    # Coach cannot bat (null batting_order / Coach role).
    assert (
        _post_delivery(
            innings.id,
            _payload(sides, 0, striker=sides.india_coach),
        ).json()["detail"]["code"]
        == "COACH_NOT_ALLOWED"
    )
    # Bowler-only playing-XI member may bat when part of the active pair —
    # first establish pair including Bumrah via replacement path is covered in
    # Phase 11 tests; here verify Bumrah is rejected only as wrong-team bowler
    # attempt already covered, and as non-active after Abhishek/Gill opened.
    assert (
        _post_delivery(
            innings.id,
            _payload(sides, 0, striker=sides.india_bowler_only),
        ).json()["detail"]["code"]
        == "PLAYER_NOT_ACTIVE"
    )
    assert (
        _post_delivery(
            innings.id,
            _payload(sides, 0, non_striker=sides.india_bowler_only),
        ).json()["detail"]["code"]
        == "PLAYER_NOT_ACTIVE"
    )

    # Non-bowler as bowler (Fakhar has Batsman only; wrong team anyway —
    # use Gill who is batsman without Bowler on batting team → wrong team.
    # Use Abhishek as bowler attempt from batting team.)
    assert (
        _post_delivery(
            innings.id,
            _payload(sides, 0, bowler=sides.striker),
        ).json()["detail"]["code"]
        == "INVALID_BOWLER_TEAM"
    )
    # Eligible batting-team dual-role player bowling for wrong side already covered.
    # Pure batsman on bowling team: Sahibzada Farhan is WK+Batsman, no Bowler.
    farhan = db.scalar(
        select(Player)
        .where(Player.team_id == sides.pakistan.id, Player.name == "Sahibzada Farhan")
        .options(selectinload(Player.roles))
    )
    assert farhan is not None
    assert (
        _post_delivery(
            innings.id,
            _payload(sides, 0, bowler=farhan),
        ).json()["detail"]["code"]
        == "PLAYER_NOT_BOWLER"
    )

    missing = _post_delivery(
        innings.id,
        {
            "striker_id": str(uuid.uuid4()),
            "non_striker_id": str(sides.non_striker.id),
            "bowler_id": str(sides.bowler.id),
            "bat_runs": 0,
        },
    )
    assert missing.status_code == 404


# --- State validation ---


def test_state_validation(db: Session, seeded: SeededSides) -> None:
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
    # CREATED match with fabricated IN_PROGRESS innings → reject on match status.
    fabricated = Innings(
        match_id=match.id,
        batting_team_id=seeded.india.id,
        innings_number=1,
        status=InningsStatus.IN_PROGRESS,
    )
    db.add(fabricated)
    db.commit()
    db.refresh(fabricated)
    assert _post_delivery(fabricated.id, _payload(seeded, 0)).status_code == 409

    # Clean fabricated and start properly.
    db.execute(delete(Innings).where(Innings.id == fabricated.id))
    db.commit()

    match = start_match(db, match.id)
    innings_1 = match.innings[0].id

    # NOT_STARTED: fabricate second innings row with NOT_STARTED while match IN_PROGRESS.
    not_started = Innings(
        match_id=match.id,
        batting_team_id=seeded.pakistan.id,
        innings_number=2,
        status=InningsStatus.NOT_STARTED,
    )
    db.add(not_started)
    db.commit()
    db.refresh(not_started)
    assert _post_delivery(not_started.id, _payload(seeded, 0)).status_code == 409
    db.execute(delete(Innings).where(Innings.id == not_started.id))
    db.commit()

    for _ in range(6):
        assert _post_delivery(innings_1, _payload(seeded, 0)).status_code == 200

    # Completed innings + INNINGS_BREAK
    assert _post_delivery(innings_1, _payload(seeded, 0)).status_code == 409

    match = start_next_innings(db, match.id)
    innings_2 = next(i for i in match.innings if i.innings_number == 2)
    pak = {
        "striker_id": str(seeded.pakistan_batter.id),
        "non_striker_id": str(
            db.scalar(
                select(Player).where(
                    Player.team_id == seeded.pakistan.id,
                    Player.name == "Saim Ayub",
                )
            ).id
        ),
        "bowler_id": str(seeded.india_bowler_only.id),
        "bat_runs": 0,
    }
    for _ in range(6):
        assert _post_delivery(innings_2.id, pak).status_code == 200

    # Match COMPLETED
    assert _post_delivery(innings_2.id, pak).status_code == 409
    assert client.get(f"{MATCHES_URL}/{match.id}").json()["status"] == "COMPLETED"

    # Missing innings
    assert _post_delivery(uuid.uuid4(), _payload(seeded, 0)).status_code == 404

    before = db.scalar(
        select(func.count()).select_from(Delivery).where(Delivery.innings_id == innings_2.id)
    )
    failed = _post_delivery(innings_2.id, pak)
    assert failed.status_code == 409
    after = db.scalar(
        select(func.count()).select_from(Delivery).where(Delivery.innings_id == innings_2.id)
    )
    assert before == after == 6

    _cleanup_match(db, match.id)


# --- Concurrency ---


def test_concurrent_deliveries_unique_positions(
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
    innings_id = str(match.innings[0].id)
    body = _payload(seeded, 1)

    def _one() -> int:
        with TestClient(app) as local:
            return local.post(
                f"/api/v1/innings/{innings_id}/deliveries", json=body
            ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _: _one(), range(8)))

    assert codes.count(200) == 8
    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(Delivery)
                .where(Delivery.innings_id == uuid.UUID(innings_id))
                .order_by(Delivery.sequence_no)
            )
        )
        assert len(rows) == 8
        assert [r.sequence_no for r in rows] == list(range(1, 9))
        positions = {(r.over_number, r.ball_in_over) for r in rows}
        assert len(positions) == 8

    _cleanup_match(db, match.id)


def test_concurrent_final_delivery_atomic(
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
        assert _post_delivery(innings_id, _payload(seeded, 0)).status_code == 200

    body = _payload(seeded, 1)
    iid = str(innings_id)

    def _final() -> int:
        with TestClient(app) as local:
            return local.post(f"/api/v1/innings/{iid}/deliveries", json=body).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: _final(), range(2)))

    assert sorted(codes) in ([200, 409], [409, 200])
    with SessionLocal() as session:
        count = session.scalar(
            select(func.count())
            .select_from(Delivery)
            .where(Delivery.innings_id == innings_id)
        )
        assert count == 6
        innings = session.get(Innings, innings_id)
        match_row = session.get(Match, match.id)
        assert innings is not None and match_row is not None
        assert innings.status is InningsStatus.COMPLETED
        assert match_row.status is MatchStatus.INNINGS_BREAK

    _cleanup_match(db, match.id)


def test_failed_validation_leaves_no_delivery(
    started_custom: tuple[Match, Innings, SeededSides],
    db: Session,
) -> None:
    _, innings, sides = started_custom
    before = db.scalar(
        select(func.count()).select_from(Delivery).where(Delivery.innings_id == innings.id)
    )
    bad = _post_delivery(innings.id, _payload(sides, 0, striker=sides.india_coach))
    assert bad.status_code == 400
    db.expire_all()
    after = db.scalar(
        select(func.count()).select_from(Delivery).where(Delivery.innings_id == innings.id)
    )
    assert before == after


def test_odd_run_rotates_strikers_for_next_ball(
    started_custom: tuple[Match, Innings, SeededSides],
    db: Session,
) -> None:
    match, innings, sides = started_custom
    first = _post_delivery(innings.id, _payload(sides, 1))
    assert first.status_code == 200

    db.expire_all()
    inn = db.get(Innings, innings.id)
    assert inn is not None
    # After 1 run, non-striker takes strike.
    assert inn.striker_id == sides.non_striker.id
    assert inn.non_striker_id == sides.striker.id

    # Match read reflects the rotated pair (Viewer/Admin live source).
    detail = client.get(f"{MATCHES_URL}/{match.id}")
    assert detail.status_code == 200
    active = detail.json()["innings"][0]
    assert active["striker"]["id"] == str(sides.non_striker.id)
    assert active["non_striker"]["id"] == str(sides.striker.id)


def test_even_run_keeps_striker(
    started_custom: tuple[Match, Innings, SeededSides],
    db: Session,
) -> None:
    _, innings, sides = started_custom
    first = _post_delivery(innings.id, _payload(sides, 2))
    assert first.status_code == 200
    db.expire_all()
    inn = db.get(Innings, innings.id)
    assert inn is not None
    assert inn.striker_id == sides.striker.id
    assert inn.non_striker_id == sides.non_striker.id


def test_end_of_over_rotates_after_dot(
    started_custom: tuple[Match, Innings, SeededSides],
    db: Session,
) -> None:
    _, innings, sides = started_custom
    striker = sides.striker
    non = sides.non_striker
    for _ in range(5):
        resp = _post_delivery(
            innings.id,
            _payload(sides, 0, striker=striker, non_striker=non),
        )
        assert resp.status_code == 200
        # Dots do not swap mid-over.
        db.expire_all()
        inn = db.get(Innings, innings.id)
        assert inn is not None
        assert inn.striker_id == striker.id
        assert inn.non_striker_id == non.id

    sixth = _post_delivery(
        innings.id,
        _payload(sides, 0, striker=striker, non_striker=non),
    )
    assert sixth.status_code == 200
    db.expire_all()
    inn = db.get(Innings, innings.id)
    assert inn is not None
    assert inn.striker_id == non.id
    assert inn.non_striker_id == striker.id
