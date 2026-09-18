"""Team domain model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UuidPrimaryKeyMixin
from app.db.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from app.db.models.player import Player


class Team(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("name", name="uq_teams_name"),
        UniqueConstraint("short_code", name="uq_teams_short_code"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    short_code: Mapped[str] = mapped_column(String(8), nullable=False)
    flag_url: Mapped[str] = mapped_column(String(512), nullable=False)

    players: Mapped[list[Player]] = relationship(
        back_populates="team",
        cascade="save-update",
    )
