"""Wickets + batter replacement tests (Phase 11)."""

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
from app.db.models import Delivery, Innings, Match, Player, Team
from app.db.seed import seed_database
from app.db.session import SessionLocal
from app.main import app
from app.schemas.match import MatchCreateRequest
from app.services.matches import create_match, start_match, start_next_innings

client = TestClient(app)


@dataclass
class SeededSides:
    india: Team
    pakistan: Team
    striker: Player
    non_striker: Player
    bowler: Player
    india_batters: list[Player]
    india_coach: Player
    india_bowler_only: Player
    pakistan_batter: Player
    pakistan_coach: Player


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

    india_players = list(
        db.scalars(
            select(Player)
            .where(Player.team_id == india.id)
            .options(selectinload(Player.roles))
        )
    )
    # Playing XI = non-null batting_order (11 players); coach excluded.
    batters = [p for p in india_players if p.batting_order is not None]
    batters.sort(key=lambda p: (p.batting_order or 99, p.name))

    return SeededSides(
        india=india,
        pakistan=pakistan,
        striker=by_name(india.id, "Abhishek Sharma"),
        non_striker=by_name(india.id, "Shubman Gill"),
        bowler=by_name(pakistan.id, "Shaheen Afridi"),
        india_batters=batters,
        india_coach=by_name(india.id, "Gautam Gambhir"),
        india_bowler_only=by_name(india.id, "Jasprit Bumrah"),
        pakistan_batter=by_name(pakistan.id, "Fakhar Zaman"),
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
            overs=20,
        ),
    )
    match = start_match(db, match.id)
    innings = next(i for i in match.innings if i.innings_number == 1)
    yield match, innings, seeded
    _cleanup_match(db, match.id)


def _base(sides: SeededSides, *, striker: Player | None = None, non_striker: Player | None = None) -> dict:
    return {
        "striker_id": str((striker or sides.striker).id),
        "non_striker_id": str((non_striker or sides.non_striker).id),
        "bowler_id": str(sides.bowler.id),
    }


def _post_delivery(innings_id: uuid.UUID, body: dict):
    return client.post(f"/api/v1/innings/{innings_id}/deliveries", json=body)


def _post_replacement(innings_id: uuid.UUID, player_id: uuid.UUID):
    return client.post(
        f"/api/v1/innings/{innings_id}/replacement",
        json={"player_id": str(player_id)},
    )


def _normal_wicket(
    sides: SeededSides,
    *,
    dismissed: Player,
    dismissal: str = "BOWLED",
    bat_runs: int = 0,
    striker: Player | None = None,
    non_striker: Player | None = None,
) -> dict:
    return {
        **_base(sides, striker=striker, non_striker=non_striker),
        "delivery_type": "NORMAL",
        "bat_runs": bat_runs,
        "wicket": {
            "dismissed_player_id": str(dismissed.id),
            "dismissal_type": dismissal,
        },
    }


# --- Basic wickets ---


@pytest.mark.parametrize(
    "dismissal",
    ["BOWLED", "CAUGHT", "LBW", "RUN_OUT", "STUMPED"],
)
def test_normal_wicket_types(
    started: tuple[Match, Innings, SeededSides],
    dismissal: str,
) -> None:
    _, innings, sides = started
    # Fresh pair each time via fixture; first ball establishes actives then wicket.
    data = _post_delivery(
        innings.id,
        _normal_wicket(sides, dismissed=sides.striker, dismissal=dismissal),
    ).json()
    assert data["is_legal"] is True
    assert data["wicket"]["dismissal_type"] == dismissal
    assert data["wicket"]["dismissed_player"]["id"] == str(sides.striker.id)
    assert data["replacement_required"] is True
    assert data["innings_status"] == InningsStatus.IN_PROGRESS.value


def test_non_striker_dismissal_and_runs(
    started: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started
    data = _post_delivery(
        innings.id,
        _normal_wicket(
            sides,
            dismissed=sides.non_striker,
            dismissal="RUN_OUT",
            bat_runs=1,
        ),
    ).json()
    assert data["total_runs"] == 1
    assert data["wicket"]["dismissed_player"]["id"] == str(sides.non_striker.id)
    assert data["replacement_required"] is True


def test_hit_wicket_rejected(
    started: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started
    resp = _post_delivery(
        innings.id,
        _normal_wicket(sides, dismissed=sides.striker, dismissal="HIT_WICKET"),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_DISMISSAL_TYPE"


# --- Free Hit ---


def test_free_hit_rejects_wicket_without_mutation(
    started: tuple[Match, Innings, SeededSides],
    db: Session,
) -> None:
    _, innings, sides = started
    assert _post_delivery(
        innings.id,
        {**_base(sides), "delivery_type": "NO_BALL", "bat_runs": 0},
    ).status_code == 200

    before = db.scalar(
        select(func.count()).select_from(Delivery).where(Delivery.innings_id == innings.id)
    )
    bad = _post_delivery(
        innings.id,
        _normal_wicket(sides, dismissed=sides.striker, dismissal="BOWLED"),
    )
    assert bad.status_code == 409
    assert bad.json()["detail"]["code"] == "WICKET_NOT_ALLOWED_ON_FREE_HIT"
    db.expire_all()
    after = db.scalar(
        select(func.count()).select_from(Delivery).where(Delivery.innings_id == innings.id)
    )
    assert before == after

    # Free Hit normal without wicket succeeds and consumes
    ok = _post_delivery(
        innings.id,
        {**_base(sides), "delivery_type": "NORMAL", "bat_runs": 0},
    ).json()
    assert ok["is_free_hit"] is True
    assert ok["wicket"] is None

    wide = _post_delivery(
        innings.id,
        {
            **_base(sides),
            "delivery_type": "WIDE",
            "bat_runs": 0,
            "extra_runs": 1,
        },
    )
    # need another free hit first
    _post_delivery(innings.id, {**_base(sides), "delivery_type": "NO_BALL", "bat_runs": 0})
    fh_wide = _post_delivery(
        innings.id,
        {**_base(sides), "delivery_type": "WIDE", "bat_runs": 0, "extra_runs": 1},
    ).json()
    assert fh_wide["is_free_hit"] is True
    assert fh_wide["is_legal"] is False

    _post_delivery(innings.id, {**_base(sides), "delivery_type": "NO_BALL", "bat_runs": 0})
    fh_nb = _post_delivery(
        innings.id,
        {**_base(sides), "delivery_type": "NO_BALL", "bat_runs": 1},
    ).json()
    assert fh_nb["is_free_hit"] is True
    nxt = _post_delivery(
        innings.id,
        {**_base(sides), "delivery_type": "NORMAL", "bat_runs": 0},
    ).json()
    assert nxt["is_free_hit"] is True


# --- Replacement ---


def test_replacement_flow(
    started: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started
    wicket = _post_delivery(
        innings.id,
        _normal_wicket(sides, dismissed=sides.striker),
    ).json()
    assert wicket["replacement_required"] is True

    blocked = _post_delivery(
        innings.id,
        {**_base(sides), "delivery_type": "NORMAL", "bat_runs": 0},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "REPLACEMENT_REQUIRED"

    replacement = next(
        p for p in sides.india_batters if p.id not in {sides.striker.id, sides.non_striker.id}
    )
    done = _post_replacement(innings.id, replacement.id)
    assert done.status_code == 200
    body = done.json()
    inn = body["innings"][0]
    assert inn["replacement_required"] is False
    active_ids = {
        inn["striker"]["id"] if inn["striker"] else None,
        inn["non_striker"]["id"] if inn["non_striker"] else None,
    }
    assert str(replacement.id) in active_ids
    assert str(sides.non_striker.id) in active_ids
    assert str(sides.striker.id) not in active_ids

    # Next delivery with new pair
    resp = _post_delivery(
        innings.id,
        {
            **_base(sides, striker=replacement, non_striker=sides.non_striker),
            "delivery_type": "NORMAL",
            "bat_runs": 1,
        },
    )
    assert resp.status_code == 200

    # Invalid replacements
    assert _post_replacement(innings.id, sides.striker.id).status_code == 409  # not required

    # New wicket to re-open replacement checks
    _post_delivery(
        innings.id,
        _normal_wicket(
            sides,
            dismissed=replacement,
            striker=replacement,
            non_striker=sides.non_striker,
        ),
    )
    assert _post_replacement(innings.id, sides.striker.id).status_code == 400  # dismissed
    assert _post_replacement(innings.id, sides.non_striker.id).status_code == 400  # active
    assert _post_replacement(innings.id, sides.india_coach.id).status_code == 400
    assert _post_replacement(innings.id, sides.pakistan_batter.id).status_code == 400
    # Bowler-only playing-XI member IS eligible as replacement.
    assert _post_replacement(innings.id, sides.india_bowler_only.id).status_code == 200


# --- Delivery type + wicket combinations ---


def test_wicket_delivery_type_rules(
    started: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started
    # Establish actives without wicket
    _post_delivery(innings.id, {**_base(sides), "delivery_type": "NORMAL", "bat_runs": 0})

    for dtype, extra in (
        ("WIDE", {"extra_runs": 1}),
        ("BYE", {"extra_runs": 1}),
        ("LEG_BYE", {"extra_runs": 1}),
    ):
        resp = _post_delivery(
            innings.id,
            {
                **_base(sides),
                "delivery_type": dtype,
                "bat_runs": 0,
                **extra,
                "wicket": {
                    "dismissed_player_id": str(sides.striker.id),
                    "dismissal_type": "RUN_OUT",
                },
            },
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "WICKET_NOT_ALLOWED_FOR_DELIVERY_TYPE"

    # NO_BALL + BOWLED rejected
    bad_nb = _post_delivery(
        innings.id,
        {
            **_base(sides),
            "delivery_type": "NO_BALL",
            "bat_runs": 0,
            "wicket": {
                "dismissed_player_id": str(sides.striker.id),
                "dismissal_type": "BOWLED",
            },
        },
    )
    assert bad_nb.status_code == 400

    # NO_BALL + RUN_OUT allowed (illegal delivery)
    ok = _post_delivery(
        innings.id,
        {
            **_base(sides),
            "delivery_type": "NO_BALL",
            "bat_runs": 0,
            "wicket": {
                "dismissed_player_id": str(sides.striker.id),
                "dismissal_type": "RUN_OUT",
            },
        },
    ).json()
    assert ok["is_legal"] is False
    assert ok["no_ball_runs"] == 1
    assert ok["wicket"]["dismissal_type"] == "RUN_OUT"
    assert ok["replacement_required"] is True
    # Free Hit still created for next opportunity after replacement
    repl = next(
        p
        for p in sides.india_batters
        if p.id not in {sides.striker.id, sides.non_striker.id}
    )
    _post_replacement(innings.id, repl.id)
    fh = _post_delivery(
        innings.id,
        {
            **_base(sides, striker=repl, non_striker=sides.non_striker),
            "delivery_type": "NORMAL",
            "bat_runs": 0,
        },
    ).json()
    assert fh["is_free_hit"] is True


# --- All-out ---


def test_all_out_completes_innings(
    db: Session, seeded: SeededSides
) -> None:
    match = create_match(
        db,
        MatchCreateRequest(
            team_1_id=seeded.india.id,
            team_2_id=seeded.pakistan.id,
            format=MatchFormat.CUSTOM,
            batting_first_team_id=seeded.india.id,
            overs=50,
        ),
    )
    match = start_match(db, match.id)
    innings_id = match.innings[0].id

    batters = list(seeded.india_batters)
    striker = batters[0]
    non_striker = batters[1]
    bench = batters[2:]

    def bowl(striker_p: Player, non_p: Player, dismissed: Player) -> dict:
        return _post_delivery(
            innings_id,
            {
                "striker_id": str(striker_p.id),
                "non_striker_id": str(non_p.id),
                "bowler_id": str(seeded.bowler.id),
                "delivery_type": "NORMAL",
                "bat_runs": 0,
                "wicket": {
                    "dismissed_player_id": str(dismissed.id),
                    "dismissal_type": "BOWLED",
                },
            },
        ).json()

    # Keep dismissing until all-out (no eligible replacement).
    active_a, active_b = striker, non_striker
    next_bench = list(bench)
    last = None
    for _ in range(20):
        last = bowl(active_a, active_b, active_a)
        if last["innings_status"] == InningsStatus.COMPLETED.value:
            break
        assert last["replacement_required"] is True
        assert next_bench, "ran out of bench unexpectedly before all-out"
        repl = next_bench.pop(0)
        assert _post_replacement(innings_id, repl.id).status_code == 200
        active_a, active_b = repl, active_b

    assert last is not None
    assert last["innings_status"] == InningsStatus.COMPLETED.value
    assert last["match_status"] == MatchStatus.INNINGS_BREAK.value
    assert last["replacement_required"] is False
    assert _post_delivery(
        innings_id,
        {
            "striker_id": str(active_a.id),
            "non_striker_id": str(active_b.id),
            "bowler_id": str(seeded.bowler.id),
            "delivery_type": "NORMAL",
            "bat_runs": 0,
        },
    ).status_code == 409

    # Coach never used
    with SessionLocal() as session:
        dismissed_ids = set(
            session.scalars(
                select(Delivery.dismissed_player_id).where(
                    Delivery.innings_id == innings_id,
                    Delivery.dismissed_player_id.is_not(None),
                )
            )
        )
        assert seeded.india_coach.id not in dismissed_ids

    # Innings 2 all-out completes match
    match = start_next_innings(db, match.id)
    innings_2 = next(i for i in match.innings if i.innings_number == 2)
    pak_batters = list(
        db.scalars(
            select(Player)
            .where(Player.team_id == seeded.pakistan.id)
            .options(selectinload(Player.roles))
        )
    )
    pak_xi = [p for p in pak_batters if p.batting_order is not None]
    pak_xi.sort(key=lambda p: (p.batting_order or 99))
    a, b = pak_xi[0], pak_xi[1]
    bench2 = pak_xi[2:]
    india_bowler = seeded.india_bowler_only
    last2 = None
    for _ in range(20):
        last2 = _post_delivery(
            innings_2.id,
            {
                "striker_id": str(a.id),
                "non_striker_id": str(b.id),
                "bowler_id": str(india_bowler.id),
                "delivery_type": "NORMAL",
                "bat_runs": 0,
                "wicket": {
                    "dismissed_player_id": str(a.id),
                    "dismissal_type": "CAUGHT",
                },
            },
        ).json()
        if last2["innings_status"] == "COMPLETED":
            break
        repl = bench2.pop(0)
        assert _post_replacement(innings_2.id, repl.id).status_code == 200
        a, b = repl, b

    assert last2 is not None
    assert last2["match_status"] == MatchStatus.COMPLETED.value
    _cleanup_match(db, match.id)


# --- Concurrency ---


def test_concurrent_replacement_once(
    started: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started
    _post_delivery(innings.id, _normal_wicket(sides, dismissed=sides.striker))
    candidates = [
        p
        for p in sides.india_batters
        if p.id not in {sides.striker.id, sides.non_striker.id}
    ][:2]
    iid = str(innings.id)

    def _replace(player_id: uuid.UUID) -> int:
        with TestClient(app) as local:
            return local.post(
                f"/api/v1/innings/{iid}/replacement",
                json={"player_id": str(player_id)},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda p: _replace(p.id), candidates))

    assert sorted(codes) in ([200, 409], [409, 200])
    with SessionLocal() as session:
        row = session.get(Innings, innings.id)
        assert row is not None
        assert row.replacement_required is False
        actives = {row.striker_id, row.non_striker_id}
        assert None not in actives
        assert sides.non_striker.id in actives
        assert len(actives & {c.id for c in candidates}) == 1


def test_dismissed_cannot_return(
    started: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started
    _post_delivery(innings.id, _normal_wicket(sides, dismissed=sides.striker))
    repl = next(
        p for p in sides.india_batters if p.id not in {sides.striker.id, sides.non_striker.id}
    )
    _post_replacement(innings.id, repl.id)
    bad = _post_delivery(
        innings.id,
        {
            **_base(sides, striker=sides.striker, non_striker=sides.non_striker),
            "delivery_type": "NORMAL",
            "bat_runs": 0,
        },
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] in {
        "PLAYER_ALREADY_DISMISSED",
        "PLAYER_NOT_ACTIVE",
    }


def test_playing_xi_has_eleven_eligible(
    db: Session, seeded: SeededSides
) -> None:
    assert len(seeded.india_batters) == 11
    assert all(p.batting_order is not None for p in seeded.india_batters)
    assert seeded.india_coach.batting_order is None

    pak_xi = list(
        db.scalars(
            select(Player).where(
                Player.team_id == seeded.pakistan.id,
                Player.batting_order.is_not(None),
            )
        )
    )
    assert len(pak_xi) == 11


@pytest.mark.parametrize(
    "name",
    ["Kuldeep Yadav", "Jasprit Bumrah", "Varun Chakaravarthy"],
)
def test_india_bowler_only_can_replace(
    started: tuple[Match, Innings, SeededSides],
    db: Session,
    name: str,
) -> None:
    _, innings, sides = started
    bowler_batter = db.scalar(
        select(Player)
        .where(Player.team_id == sides.india.id, Player.name == name)
        .options(selectinload(Player.roles))
    )
    assert bowler_batter is not None
    assert bowler_batter.batting_order is not None
    assert "Batsman" not in {r.name for r in bowler_batter.roles}
    assert "Bowler" in {r.name for r in bowler_batter.roles}

    _post_delivery(innings.id, _normal_wicket(sides, dismissed=sides.striker))
    resp = _post_replacement(innings.id, bowler_batter.id)
    assert resp.status_code == 200
    inn = resp.json()["innings"][0]
    assert inn["replacement_required"] is False
    active = {inn["striker"]["id"], inn["non_striker"]["id"]}
    assert str(bowler_batter.id) in active


@pytest.mark.parametrize(
    "name",
    ["Shaheen Afridi", "Haris Rauf", "Abrar Ahmed"],
)
def test_pakistan_bowler_only_can_replace_when_batting(
    db: Session, seeded: SeededSides, name: str
) -> None:
    match = create_match(
        db,
        MatchCreateRequest(
            team_1_id=seeded.india.id,
            team_2_id=seeded.pakistan.id,
            format=MatchFormat.CUSTOM,
            batting_first_team_id=seeded.pakistan.id,
            overs=5,
        ),
    )
    match = start_match(db, match.id)
    innings = match.innings[0]
    pak_xi = list(
        db.scalars(
            select(Player)
            .where(
                Player.team_id == seeded.pakistan.id,
                Player.batting_order.is_not(None),
            )
            .order_by(Player.batting_order)
        )
    )
    striker, non_striker = pak_xi[0], pak_xi[1]
    bowler_batter = next(p for p in pak_xi if p.name == name)
    assert "Batsman" not in {
        r.name
        for r in db.scalar(
            select(Player)
            .where(Player.id == bowler_batter.id)
            .options(selectinload(Player.roles))
        ).roles
    }

    _post_delivery(
        innings.id,
        {
            "striker_id": str(striker.id),
            "non_striker_id": str(non_striker.id),
            "bowler_id": str(seeded.india_bowler_only.id),
            "delivery_type": "NORMAL",
            "bat_runs": 0,
            "wicket": {
                "dismissed_player_id": str(striker.id),
                "dismissal_type": "BOWLED",
            },
        },
    )
    resp = _post_replacement(innings.id, bowler_batter.id)
    assert resp.status_code == 200
    _cleanup_match(db, match.id)


def test_bowler_only_replacement_then_delivery(
    started: tuple[Match, Innings, SeededSides],
) -> None:
    _, innings, sides = started
    wicket = _post_delivery(
        innings.id,
        _normal_wicket(sides, dismissed=sides.striker),
    ).json()
    assert wicket["replacement_required"] is True
    assert (
        _post_delivery(
            innings.id,
            {**_base(sides), "delivery_type": "NORMAL", "bat_runs": 0},
        ).status_code
        == 409
    )

    assert _post_replacement(innings.id, sides.india_bowler_only.id).status_code == 200
    detail = client.get(f"/api/v1/matches/{innings.match_id}").json()
    inn = detail["innings"][0]
    assert inn["replacement_required"] is False
    active = {inn["striker"]["id"], inn["non_striker"]["id"]}
    assert str(sides.india_bowler_only.id) in active
    assert str(sides.non_striker.id) in active
    assert len(active) == 2

    nxt = _post_delivery(
        innings.id,
        {
            **_base(
                sides,
                striker=sides.india_bowler_only,
                non_striker=sides.non_striker,
            ),
            "delivery_type": "NORMAL",
            "bat_runs": 1,
        },
    )
    assert nxt.status_code == 200
    assert nxt.json()["striker"]["id"] == str(sides.india_bowler_only.id)
