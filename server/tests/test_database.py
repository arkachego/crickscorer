"""Database connectivity and PostgreSQL capability tests.

These tests require PostgreSQL reachable via DATABASE_URL (Compose service `db`).
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


def test_database_connection() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar_one()
    assert result == 1


def test_postgresql_version_is_18_3() -> None:
    with engine.connect() as conn:
        version = conn.execute(text("SHOW server_version")).scalar_one()
    assert str(version).startswith("18.3")


def test_uuidv7_native_generation() -> None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                  uuidv7() AS id,
                  pg_typeof(uuidv7())::text AS typ,
                  uuid_extract_version(uuidv7()) AS ver
                """
            )
        ).mappings().one()

    assert row["typ"] == "uuid"
    assert int(row["ver"]) == 7
    assert row["id"] is not None
