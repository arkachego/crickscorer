"""Domain model, seed, constraint, and UUIDv7 tests (Phase 4 corrective)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.enums import DismissalType, MatchFormat, MatchStatus
from app.db.models import Delivery, Innings, Match, Player, Role, Team, player_role
from app.db.seed import (
    AFGHANISTAN_FLAG_URL,
    AFGHANISTAN_ROSTER,
    BANGLADESH_FLAG_URL,
    BANGLADESH_ROSTER,
    INDIA_FLAG_URL,
    PAKISTAN_FLAG_URL,
    ROLE_NAMES,
    SRI_LANKA_FLAG_URL,
    SRI_LANKA_ROSTER,
    TEAM_SPECS,
    expected_player_count,
    expected_player_role_mapping_count,
    expected_team_count,
    seed_database,
)
from app.db.session import SessionLocal, engine

PLAYING_ROLES = {"Batsman", "Bowler", "Wicket Keeper", "Captain", "Vice-Captain"}


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _uuid_version(value: uuid.UUID) -> int:
    return value.version if value.version is not None else 0


def _role_names(player: Player) -> set[str]:
    return {r.name for r in player.roles}


def test_seeded_roles(db: Session) -> None:
    seed_database(db)
    roles = list(db.scalars(select(Role).order_by(Role.name)))
    assert len(roles) == 6
    assert [r.name for r in roles] == sorted(ROLE_NAMES)
    assert all(_uuid_version(r.id) == 7 for r in roles)

    # Association table may register a composite pg_type; ensure it is not an enum.
    with engine.connect() as conn:
        is_enum = conn.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM pg_type t
                  JOIN pg_namespace n ON n.oid = t.typnamespace
                  WHERE n.nspname = 'public'
                    AND t.typname = 'player_role'
                    AND t.typtype = 'e'
                )
                """
            )
        ).scalar_one()
    assert is_enum is False


def test_no_incorrect_player_columns() -> None:
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("players")}
    assert "role" not in columns
    assert "is_wicketkeeper" not in columns
    assert "is_captain" not in columns
    assert not hasattr(Player, "is_captain")
    assert not hasattr(Player, "is_wicketkeeper")


def test_roles_and_player_role_tables_exist() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "roles" in tables
    assert "player_role" in tables
    pk = inspector.get_pk_constraint("player_role")
    assert set(pk["constrained_columns"]) == {"player_id", "role_id"}


def test_seed_roster_counts_and_orders(db: Session) -> None:
    seed_database(db)

    teams = list(db.scalars(select(Team).order_by(Team.short_code)))
    assert len(teams) == expected_team_count()
    by_code = {t.short_code: t for t in teams}
    assert set(by_code) == {"AFG", "BAN", "IND", "PAK", "SL"}
    assert by_code["IND"].flag_url == INDIA_FLAG_URL
    assert by_code["PAK"].flag_url == PAKISTAN_FLAG_URL
    assert by_code["BAN"].flag_url == BANGLADESH_FLAG_URL
    assert by_code["SL"].flag_url == SRI_LANKA_FLAG_URL
    assert by_code["AFG"].flag_url == AFGHANISTAN_FLAG_URL

    players = list(db.scalars(select(Player)))
    assert len(players) == expected_player_count()
    assert expected_player_count() == 60

    for _name, short_code, _flag, roster in TEAM_SPECS:
        team = by_code[short_code]
        team_players = [p for p in players if p.team_id == team.id]
        assert len(team_players) == 12

        ordered = sorted(
            [p for p in team_players if p.batting_order is not None],
            key=lambda p: p.batting_order or 0,
        )
        assert [p.batting_order for p in ordered] == list(range(1, 12))
        assert [p.name for p in ordered] == [
            r.name for r in roster if r.batting_order is not None
        ]
        for player, seed in zip(
            ordered, [r for r in roster if r.batting_order is not None], strict=True
        ):
            assert _role_names(player) == set(seed.roles)

        coaches = [p for p in team_players if p.batting_order is None]
        assert len(coaches) == 1
        assert _role_names(coaches[0]) == {"Coach"}
        assert coaches[0].name == next(
            r.name for r in roster if r.batting_order is None
        )

    mapping_count = db.execute(select(player_role.c.player_id)).all()
    assert len(mapping_count) == expected_player_role_mapping_count()


def test_seed_is_idempotent(db: Session) -> None:
    seed_database(db)
    first_teams = len(list(db.scalars(select(Team))))
    first_players = len(list(db.scalars(select(Player))))
    first_mappings = len(db.execute(select(player_role.c.player_id)).all())
    assert first_teams == expected_team_count()
    assert first_players == expected_player_count()
    assert first_mappings == expected_player_role_mapping_count()

    seed_database(db)
    assert len(list(db.scalars(select(Team)))) == first_teams
    assert len(list(db.scalars(select(Role)))) == 6
    assert len(list(db.scalars(select(Player)))) == first_players
    assert len(db.execute(select(player_role.c.player_id)).all()) == first_mappings


def test_coaches(db: Session) -> None:
    seed_database(db)
    coaches = {
        "IND": "Gautam Gambhir",
        "PAK": "Mike Hesson",
        "BAN": "Phil Simmons",
        "SL": "Sanath Jayasuriya",
        "AFG": "Jonathan Trott",
    }
    for short_code, coach_name in coaches.items():
        team = db.scalar(select(Team).where(Team.short_code == short_code))
        coach = db.scalar(select(Player).where(Player.name == coach_name))
        assert team is not None and coach is not None
        assert coach.team_id == team.id
        assert coach.batting_order is None
        assert _role_names(coach) == {"Coach"}
        assert not (_role_names(coach) & PLAYING_ROLES)


def test_leadership_and_wicketkeepers(db: Session) -> None:
    seed_database(db)

    sky = db.scalar(select(Player).where(Player.name == "Suryakumar Yadav"))
    gill = db.scalar(select(Player).where(Player.name == "Shubman Gill"))
    agha = db.scalar(select(Player).where(Player.name == "Salman Agha"))
    litton = db.scalar(select(Player).where(Player.name == "Litton Das"))
    asalanka = db.scalar(select(Player).where(Player.name == "Charith Asalanka"))
    rashid = db.scalar(select(Player).where(Player.name == "Rashid Khan"))
    assert sky and gill and agha and litton and asalanka and rashid
    assert "Captain" in _role_names(sky)
    assert "Vice-Captain" in _role_names(gill)
    assert "Captain" in _role_names(agha)
    assert "Captain" in _role_names(litton)
    assert "Captain" in _role_names(asalanka)
    assert "Captain" in _role_names(rashid)

    # No Pakistan / Bangladesh / Sri Lanka / Afghanistan vice-captain in seed.
    for short_code in ("PAK", "BAN", "SL", "AFG"):
        team = db.scalar(select(Team).where(Team.short_code == short_code))
        team_players = list(
            db.scalars(select(Player).where(Player.team_id == team.id))
        )
        assert not any("Vice-Captain" in _role_names(p) for p in team_players)

    for name in (
        "Sanju Samson",
        "Sahibzada Farhan",
        "Mohammad Haris",
        "Parvez Hossain Emon",
        "Litton Das",
        "Jaker Ali",
        "Kusal Mendis",
        "Kamil Mishara",
        "Kusal Perera",
        "Rahmanullah Gurbaz",
    ):
        player = db.scalar(select(Player).where(Player.name == name))
        assert player is not None
        assert "Wicket Keeper" in _role_names(player)


def test_expanded_asia_cup_rosters(db: Session) -> None:
    seed_database(db)

    for short_code, flag_url, roster, captain, coach in (
        ("BAN", BANGLADESH_FLAG_URL, BANGLADESH_ROSTER, "Litton Das", "Phil Simmons"),
        ("SL", SRI_LANKA_FLAG_URL, SRI_LANKA_ROSTER, "Charith Asalanka", "Sanath Jayasuriya"),
        (
            "AFG",
            AFGHANISTAN_FLAG_URL,
            AFGHANISTAN_ROSTER,
            "Rashid Khan",
            "Jonathan Trott",
        ),
    ):
        team = db.scalar(select(Team).where(Team.short_code == short_code))
        assert team is not None
        assert team.flag_url == flag_url
        team_players = list(
            db.scalars(select(Player).where(Player.team_id == team.id))
        )
        assert len(team_players) == 12
        xi = [p for p in team_players if p.batting_order is not None]
        coaches = [p for p in team_players if p.batting_order is None]
        assert len(xi) == 11
        assert len(coaches) == 1
        assert coaches[0].name == coach
        assert {p.name for p in team_players} == {r.name for r in roster}

        captain_player = next(p for p in team_players if p.name == captain)
        assert "Captain" in _role_names(captain_player)


def test_abhishek_sharma_roles(db: Session) -> None:
    seed_database(db)
    abhishek = db.scalar(select(Player).where(Player.name == "Abhishek Sharma"))
    assert abhishek is not None
    names = _role_names(abhishek)
    assert names == {"Batsman"}
    assert "Bowler" not in names


def test_entity_id_defaults_are_uuidv7_in_schema() -> None:
    with engine.connect() as conn:
        for table_name in (
            "teams",
            "roles",
            "players",
            "matches",
            "innings",
            "deliveries",
        ):
            row = conn.execute(
                text(
                    """
                    SELECT
                      format_type(a.atttypid, a.atttypmod) AS typ,
                      pg_get_expr(d.adbin, d.adrelid) AS def,
                      EXISTS (
                        SELECT 1
                        FROM pg_constraint c
                        WHERE c.conrelid = a.attrelid
                          AND c.contype = 'p'
                          AND a.attnum = ANY (c.conkey)
                      ) AS is_pk
                    FROM pg_attribute a
                    JOIN pg_class cls ON cls.oid = a.attrelid
                    JOIN pg_namespace nsp ON nsp.oid = cls.relnamespace
                    LEFT JOIN pg_attrdef d
                      ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                    WHERE nsp.nspname = 'public'
                      AND cls.relname = :table_name
                      AND a.attname = 'id'
                      AND a.attnum > 0
                      AND NOT a.attisdropped
                    """
                ),
                {"table_name": table_name},
            ).mappings().one()
            assert row["typ"] == "uuid"
            assert row["is_pk"] is True
            assert row["def"] is not None
            assert "uuidv7()" in row["def"]


def test_seeded_row_ids_are_uuid_version_7(db: Session) -> None:
    seed_database(db)
    with engine.connect() as conn:
        for table_name in ("teams", "roles", "players"):
            versions = (
                conn.execute(
                    text(f"SELECT uuid_extract_version(id) FROM {table_name}")
                )
                .scalars()
                .all()
            )
            assert versions
            assert all(int(v) == 7 for v in versions)


def test_duplicate_role_name_fails(db: Session) -> None:
    seed_database(db)
    db.add(Role(name="Batsman"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_duplicate_player_role_mapping_fails(db: Session) -> None:
    seed_database(db)
    batsman = db.scalar(select(Role).where(Role.name == "Batsman"))
    abhishek = db.scalar(select(Player).where(Player.name == "Abhishek Sharma"))
    assert batsman and abhishek
    with pytest.raises(IntegrityError):
        db.execute(
            player_role.insert().values(player_id=abhishek.id, role_id=batsman.id)
        )
        db.flush()
    db.rollback()


def test_invalid_player_role_fks_fail(db: Session) -> None:
    seed_database(db)
    batsman = db.scalar(select(Role).where(Role.name == "Batsman"))
    assert batsman is not None
    with pytest.raises(IntegrityError):
        db.execute(
            player_role.insert().values(player_id=uuid.uuid4(), role_id=batsman.id)
        )
        db.flush()
    db.rollback()

    abhishek = db.scalar(select(Player).where(Player.name == "Abhishek Sharma"))
    assert abhishek is not None
    with pytest.raises(IntegrityError):
        db.execute(
            player_role.insert().values(player_id=abhishek.id, role_id=uuid.uuid4())
        )
        db.flush()
    db.rollback()


def test_duplicate_team_short_code_fails(db: Session) -> None:
    seed_database(db)
    db.add(Team(name="India XI", short_code="IND", flag_url=INDIA_FLAG_URL))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_duplicate_batting_order_within_team_fails(db: Session) -> None:
    seed_database(db)
    india = db.scalar(select(Team).where(Team.short_code == "IND"))
    assert india is not None
    db.add(Player(team_id=india.id, name="Extra Batter", batting_order=1))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_match_identical_teams_fails(db: Session) -> None:
    seed_database(db)
    india = db.scalar(select(Team).where(Team.short_code == "IND"))
    assert india is not None
    db.add(
        Match(
            team_1_id=india.id,
            team_2_id=india.id,
            format=MatchFormat.T20,
            overs=20,
            status=MatchStatus.CREATED,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_match_invalid_overs_fails(db: Session) -> None:
    seed_database(db)
    india = db.scalar(select(Team).where(Team.short_code == "IND"))
    pakistan = db.scalar(select(Team).where(Team.short_code == "PAK"))
    assert india and pakistan
    db.add(
        Match(
            team_1_id=india.id,
            team_2_id=pakistan.id,
            format=MatchFormat.T20,
            overs=0,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_invalid_player_team_fk_fails(db: Session) -> None:
    db.add(Player(team_id=uuid.uuid4(), name="Ghost", batting_order=1))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_duplicate_innings_number_fails(db: Session) -> None:
    seed_database(db)
    india = db.scalar(select(Team).where(Team.short_code == "IND"))
    pakistan = db.scalar(select(Team).where(Team.short_code == "PAK"))
    assert india and pakistan
    match = Match(
        team_1_id=india.id,
        team_2_id=pakistan.id,
        format=MatchFormat.T20,
        overs=20,
    )
    db.add(match)
    db.flush()
    db.add(Innings(match_id=match.id, batting_team_id=india.id, innings_number=1))
    db.flush()
    db.add(Innings(match_id=match.id, batting_team_id=pakistan.id, innings_number=1))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_match_innings_delivery_structure(db: Session) -> None:
    seed_database(db)
    india = db.scalar(select(Team).where(Team.short_code == "IND"))
    pakistan = db.scalar(select(Team).where(Team.short_code == "PAK"))
    assert india and pakistan

    match = Match(
        team_1_id=india.id,
        team_2_id=pakistan.id,
        batting_first_team_id=india.id,
        format=MatchFormat.T20,
        overs=20,
    )
    db.add(match)
    db.flush()

    innings = Innings(
        match_id=match.id,
        batting_team_id=india.id,
        innings_number=1,
    )
    db.add(innings)
    db.flush()

    india_xi = list(
        db.scalars(
            select(Player)
            .where(Player.team_id == india.id, Player.batting_order.is_not(None))
            .order_by(Player.batting_order)
        )
    )
    pak_xi = list(
        db.scalars(
            select(Player)
            .where(Player.team_id == pakistan.id, Player.batting_order.is_not(None))
            .order_by(Player.batting_order)
        )
    )

    delivery = Delivery(
        innings_id=innings.id,
        sequence_no=1,
        over_number=0,
        ball_in_over=1,
        striker_id=india_xi[0].id,
        non_striker_id=india_xi[1].id,
        bowler_id=pak_xi[8].id,
        bat_runs=4,
        total_runs=4,
        is_legal=True,
    )
    db.add(delivery)
    db.flush()
    assert _uuid_version(delivery.id) == 7

    wicket = Delivery(
        innings_id=innings.id,
        sequence_no=2,
        over_number=0,
        ball_in_over=2,
        striker_id=india_xi[0].id,
        non_striker_id=india_xi[1].id,
        bowler_id=pak_xi[8].id,
        dismissal_type=DismissalType.BOWLED,
        dismissed_player_id=india_xi[0].id,
    )
    db.add(wicket)
    db.flush()
    assert wicket.dismissed_player_id == india_xi[0].id
    db.rollback()
