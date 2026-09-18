"""Innings domain model (explicit batting team; multi-innings ready)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UuidPrimaryKeyMixin
from app.db.enums import InningsStatus
from app.db.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from app.db.models.batter_replacement import BatterReplacement
    from app.db.models.delivery import Delivery
    from app.db.models.match import Match
    from app.db.models.player import Player
    from app.db.models.team import Team


class Innings(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "innings"
    __table_args__ = (
        UniqueConstraint("match_id", "innings_number", name="uq_innings_match_number"),
        CheckConstraint("innings_number >= 1", name="ck_innings_number_positive"),
        CheckConstraint(
            "target IS NULL OR target >= 0",
            name="ck_innings_target_non_negative",
        ),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    batting_team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[InningsStatus] = mapped_column(
        Enum(
            InningsStatus,
            name="innings_status",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        server_default=text("'NOT_STARTED'::innings_status"),
    )
    target: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Authoritative active batting pair (Phase 11). Null until first delivery /
    # while a slot awaits replacement after a wicket.
    striker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    non_striker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    replacement_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=false(),
    )

    match: Mapped[Match] = relationship(back_populates="innings")
    batting_team: Mapped[Team] = relationship()
    striker: Mapped[Player | None] = relationship(foreign_keys=[striker_id])
    non_striker: Mapped[Player | None] = relationship(foreign_keys=[non_striker_id])
    deliveries: Mapped[list[Delivery]] = relationship(
        back_populates="innings",
        cascade="save-update",
    )
    batter_replacements: Mapped[list[BatterReplacement]] = relationship(
        back_populates="innings",
        cascade="save-update",
    )
