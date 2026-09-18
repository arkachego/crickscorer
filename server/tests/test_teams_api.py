"""Team list API tests (Phase 6 dependency)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Team
from app.db.seed import seed_database
from app.main import app

client = TestClient(app)


def test_list_teams_returns_seeded_teams(db: Session) -> None:
    seed_database(db)
    response = client.get("/api/v1/teams")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    codes = {team["short_code"] for team in data}
    assert "IND" in codes
    assert "PAK" in codes
    for team in data:
        assert "id" in team
        assert "name" in team
        assert "short_code" in team
        assert "flag_url" in team


def test_list_teams_includes_created_team(db: Session) -> None:
    team = Team(
        name="List Probe XI",
        short_code="LPX",
        flag_url="https://example.test/lpx.svg",
    )
    db.add(team)
    db.commit()
    db.refresh(team)

    response = client.get("/api/v1/teams")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert str(team.id) in ids

    db.delete(team)
    db.commit()
