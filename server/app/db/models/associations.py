"""Association table for players ↔ roles (many-to-many)."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base

player_role = Table(
    "player_role",
    Base.metadata,
    Column(
        "player_id",
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)
