"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings loaded from the environment."""

    database_url: str


def _normalize_database_url(url: str) -> str:
    """Ensure SQLAlchemy uses the psycopg (v3) driver."""
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        raise RuntimeError("DATABASE_URL environment variable is required")
    return Settings(database_url=_normalize_database_url(raw))
