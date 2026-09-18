"""Health endpoint tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_json_ok() -> None:
    response = client.get("/health")
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"status": "ok"}
