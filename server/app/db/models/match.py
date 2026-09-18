"""Match domain model (structural; no lifecycle transitions in Phase 4)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UuidPrimaryKeyMixin
from app.db.enums import MatchFormat, MatchStatus
from app.db.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from app.db.models.innings import Innings
    from app.db.models.team import Team


class Match(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("team_1_id <> team_2_id", name="ck_matches_different_teams"),
        CheckConstraint("overs IS NULL OR overs > 0", name="ck_matches_overs_positive"),
    )

    team_1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    team_2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Membership among team_1/team_2 is enforced by the Match Creation API (Phase 5).
    batting_first_team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    format: Mapped[MatchFormat] = mapped_column(
        Enum(
            MatchFormat,
            name="match_format",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    overs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[MatchStatus] = mapped_column(
        Enum(
            MatchStatus,
            name="match_status",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=text("'CREATED'::match_status"),
    )

    team_1: Mapped[Team] = relationship(foreign_keys=[team_1_id])
    team_2: Mapped[Team] = relationship(foreign_keys=[team_2_id])
    batting_first_team: Mapped[Team | None] = relationship(
        foreign_keys=[batting_first_team_id],
    )
    innings: Mapped[list[Innings]] = relationship(
        back_populates="match",
        cascade="save-update",
    )
