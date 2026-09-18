"""
Deterministic seed for CrickScorer domain data.

Sources:
  - 2025 Men's Asia Cup Final (India vs Pakistan), 28 September 2025
  - Bangladesh vs Sri Lanka, 5th Match, Group B, Asia Cup 2025, 13 September 2025
  - Afghanistan vs Hong Kong, 1st Match, Group B, Asia Cup 2025, 9 September 2025

Each team includes the Head Coach as the 12th person:
  India       → Gautam Gambhir (Coach)
  Pakistan    → Mike Hesson (Coach)
  Bangladesh  → Phil Simmons (Coach)
  Sri Lanka   → Sanath Jayasuriya (Coach)
  Afghanistan → Jonathan Trott (Coach)

Roles are relational (`roles` + `player_role`), not an enum.

Usage:

  python -m app.db.seed
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Player, Role, Team
from app.db.session import SessionLocal

INDIA_FLAG_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/4/41/Flag_of_India.svg"
)
PAKISTAN_FLAG_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/3/32/Flag_of_Pakistan.svg"
)
BANGLADESH_FLAG_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/f/f9/Flag_of_Bangladesh.svg"
)
SRI_LANKA_FLAG_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/1/11/Flag_of_Sri_Lanka.svg"
)
AFGHANISTAN_FLAG_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/"
    "c/cd/Flag_of_Afghanistan_%282013%E2%80%932021%29.svg"
)

ROLE_NAMES: tuple[str, ...] = (
    "Batsman",
    "Bowler",
    "Wicket Keeper",
    "Captain",
    "Vice-Captain",
    "Coach",
)


@dataclass(frozen=True, slots=True)
class SeedPerson:
    name: str
    batting_order: int | None
    roles: tuple[str, ...]


INDIA_ROSTER: tuple[SeedPerson, ...] = (
    SeedPerson("Abhishek Sharma", 1, ("Batsman",)),
    SeedPerson("Shubman Gill", 2, ("Batsman", "Vice-Captain")),
    SeedPerson("Suryakumar Yadav", 3, ("Batsman", "Captain")),
    SeedPerson("Tilak Varma", 4, ("Batsman",)),
    SeedPerson("Sanju Samson", 5, ("Batsman", "Wicket Keeper")),
    SeedPerson("Shivam Dube", 6, ("Batsman", "Bowler")),
    SeedPerson("Rinku Singh", 7, ("Batsman",)),
    SeedPerson("Axar Patel", 8, ("Batsman", "Bowler")),
    SeedPerson("Kuldeep Yadav", 9, ("Bowler",)),
    SeedPerson("Jasprit Bumrah", 10, ("Bowler",)),
    SeedPerson("Varun Chakaravarthy", 11, ("Bowler",)),
    SeedPerson("Gautam Gambhir", None, ("Coach",)),
)

PAKISTAN_ROSTER: tuple[SeedPerson, ...] = (
    SeedPerson("Sahibzada Farhan", 1, ("Batsman", "Wicket Keeper")),
    SeedPerson("Fakhar Zaman", 2, ("Batsman",)),
    SeedPerson("Saim Ayub", 3, ("Batsman", "Bowler")),
    SeedPerson("Salman Agha", 4, ("Batsman", "Captain")),
    SeedPerson("Hussain Talat", 5, ("Batsman", "Bowler")),
    SeedPerson("Mohammad Haris", 6, ("Batsman", "Wicket Keeper")),
    SeedPerson("Mohammad Nawaz", 7, ("Batsman", "Bowler")),
    SeedPerson("Faheem Ashraf", 8, ("Batsman", "Bowler")),
    SeedPerson("Shaheen Afridi", 9, ("Bowler",)),
    SeedPerson("Haris Rauf", 10, ("Bowler",)),
    SeedPerson("Abrar Ahmed", 11, ("Bowler",)),
    SeedPerson("Mike Hesson", None, ("Coach",)),
)

BANGLADESH_ROSTER: tuple[SeedPerson, ...] = (
    SeedPerson("Parvez Hossain Emon", 1, ("Batsman", "Wicket Keeper")),
    SeedPerson("Tanzid Hasan", 2, ("Batsman",)),
    SeedPerson("Litton Das", 3, ("Batsman", "Wicket Keeper", "Captain")),
    SeedPerson("Towhid Hridoy", 4, ("Batsman",)),
    SeedPerson("Jaker Ali", 5, ("Batsman", "Wicket Keeper")),
    SeedPerson("Shamim Hossain", 6, ("Batsman", "Bowler")),
    SeedPerson("Mahedi Hasan", 7, ("Batsman", "Bowler")),
    SeedPerson("Rishad Hossain", 8, ("Bowler",)),
    SeedPerson("Tanzim Hasan Sakib", 9, ("Bowler",)),
    SeedPerson("Shoriful Islam", 10, ("Bowler",)),
    SeedPerson("Mustafizur Rahman", 11, ("Bowler",)),
    SeedPerson("Phil Simmons", None, ("Coach",)),
)

SRI_LANKA_ROSTER: tuple[SeedPerson, ...] = (
    SeedPerson("Pathum Nissanka", 1, ("Batsman",)),
    SeedPerson("Kusal Mendis", 2, ("Batsman", "Wicket Keeper")),
    SeedPerson("Kamil Mishara", 3, ("Batsman", "Wicket Keeper")),
    SeedPerson("Kusal Perera", 4, ("Batsman", "Wicket Keeper")),
    SeedPerson("Charith Asalanka", 5, ("Batsman", "Bowler", "Captain")),
    SeedPerson("Kamindu Mendis", 6, ("Batsman", "Bowler")),
    SeedPerson("Dasun Shanaka", 7, ("Batsman", "Bowler")),
    SeedPerson("Wanindu Hasaranga", 8, ("Batsman", "Bowler")),
    SeedPerson("Dushmantha Chameera", 9, ("Bowler",)),
    SeedPerson("Matheesha Pathirana", 10, ("Bowler",)),
    SeedPerson("Nuwan Thushara", 11, ("Bowler",)),
    SeedPerson("Sanath Jayasuriya", None, ("Coach",)),
)

AFGHANISTAN_ROSTER: tuple[SeedPerson, ...] = (
    SeedPerson("Rahmanullah Gurbaz", 1, ("Batsman", "Wicket Keeper")),
    SeedPerson("Sediqullah Atal", 2, ("Batsman",)),
    SeedPerson("Ibrahim Zadran", 3, ("Batsman",)),
    SeedPerson("Gulbadin Naib", 4, ("Batsman", "Bowler")),
    SeedPerson("Azmatullah Omarzai", 5, ("Batsman", "Bowler")),
    SeedPerson("Mohammad Nabi", 6, ("Batsman", "Bowler")),
    SeedPerson("Karim Janat", 7, ("Batsman", "Bowler")),
    SeedPerson("Rashid Khan", 8, ("Batsman", "Bowler", "Captain")),
    SeedPerson("Noor Ahmad", 9, ("Bowler",)),
    SeedPerson("Allah Mohammad Ghazanfar", 10, ("Bowler",)),
    SeedPerson("Fazalhaq Farooqi", 11, ("Bowler",)),
    SeedPerson("Jonathan Trott", None, ("Coach",)),
)

ALL_ROSTERS: tuple[tuple[SeedPerson, ...], ...] = (
    INDIA_ROSTER,
    PAKISTAN_ROSTER,
    BANGLADESH_ROSTER,
    SRI_LANKA_ROSTER,
    AFGHANISTAN_ROSTER,
)

TEAM_SPECS: tuple[tuple[str, str, str, tuple[SeedPerson, ...]], ...] = (
    ("India", "IND", INDIA_FLAG_URL, INDIA_ROSTER),
    ("Pakistan", "PAK", PAKISTAN_FLAG_URL, PAKISTAN_ROSTER),
    ("Bangladesh", "BAN", BANGLADESH_FLAG_URL, BANGLADESH_ROSTER),
    ("Sri Lanka", "SL", SRI_LANKA_FLAG_URL, SRI_LANKA_ROSTER),
    ("Afghanistan", "AFG", AFGHANISTAN_FLAG_URL, AFGHANISTAN_ROSTER),
)


def expected_player_role_mapping_count() -> int:
    return sum(len(person.roles) for roster in ALL_ROSTERS for person in roster)


def expected_team_count() -> int:
    return len(TEAM_SPECS)


def expected_player_count() -> int:
    return sum(len(roster) for roster in ALL_ROSTERS)


def _upsert_team(
    session: Session,
    *,
    name: str,
    short_code: str,
    flag_url: str,
) -> Team:
    team = session.scalar(select(Team).where(Team.short_code == short_code))
    if team is None:
        team = Team(name=name, short_code=short_code, flag_url=flag_url)
        session.add(team)
        session.flush()
        return team

    team.name = name
    team.flag_url = flag_url
    session.flush()
    return team


def _upsert_roles(session: Session) -> dict[str, Role]:
    by_name: dict[str, Role] = {}
    for name in ROLE_NAMES:
        role = session.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(name=name)
            session.add(role)
            session.flush()
        by_name[name] = role
    return by_name


def _upsert_person(
    session: Session,
    team: Team,
    seed: SeedPerson,
    roles_by_name: dict[str, Role],
) -> None:
    player = session.scalar(
        select(Player).where(
            Player.team_id == team.id,
            Player.name == seed.name,
        )
    )
    if player is None:
        player = Player(
            team_id=team.id,
            name=seed.name,
            batting_order=seed.batting_order,
        )
        session.add(player)
        session.flush()
    else:
        player.batting_order = seed.batting_order

    desired = [roles_by_name[name] for name in seed.roles]
    player.roles = desired


def seed_database(session: Session) -> None:
    """Idempotently seed roles, teams, and roster records, then commit."""
    roles_by_name = _upsert_roles(session)

    for name, short_code, flag_url, roster in TEAM_SPECS:
        team = _upsert_team(
            session,
            name=name,
            short_code=short_code,
            flag_url=flag_url,
        )
        for person in roster:
            _upsert_person(session, team, person, roles_by_name)

    session.commit()


def main() -> None:
    session = SessionLocal()
    try:
        seed_database(session)
        print(
            "Seed complete: "
            f"roles={len(ROLE_NAMES)}, "
            f"teams={expected_team_count()}, "
            f"roster={expected_player_count()} "
            f"(player_role mappings={expected_player_role_mapping_count()})."
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
