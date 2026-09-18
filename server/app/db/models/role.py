"""Role reference data (ordinary table — not a PostgreSQL enum)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UuidPrimaryKeyMixin
from app.db.mixins import CreatedAtMixin
from app.db.models.associations import player_role

if TYPE_CHECKING:
    from app.db.models.player import Player


class Role(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("name", name="uq_roles_name"),)

    name: Mapped[str] = mapped_column(String(64), nullable=False)

    players: Mapped[list[Player]] = relationship(
        secondary=player_role,
        back_populates="roles",
    )
