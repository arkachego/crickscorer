"""Player / roster-person domain model.

Roles are many-to-many via `player_role`.
There is no `role`, `is_captain`, or `is_wicketkeeper` column.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UuidPrimaryKeyMixin
from app.db.mixins import CreatedAtMixin
from app.db.models.associations import player_role

if TYPE_CHECKING:
    from app.db.models.role import Role
    from app.db.models.team import Team


class Player(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("team_id", "batting_order", name="uq_players_team_batting_order"),
        UniqueConstraint("team_id", "name", name="uq_players_team_name"),
        CheckConstraint(
            "batting_order IS NULL OR batting_order >= 1",
            name="ck_players_batting_order_positive",
        ),
    )

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # NULL for coaches (non-batting roster records).
    batting_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    team: Mapped[Team] = relationship(back_populates="players")
    roles: Mapped[list[Role]] = relationship(
        secondary=player_role,
        back_populates="players",
    )
