"""Delivery domain model (rich event structure for future scoring)."""

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
from app.db.enums import DismissalType
from app.db.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from app.db.models.innings import Innings
    from app.db.models.player import Player


class Delivery(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint(
            "innings_id",
            "sequence_no",
            name="uq_deliveries_innings_sequence",
        ),
        CheckConstraint("sequence_no >= 1", name="ck_deliveries_sequence_positive"),
        CheckConstraint("over_number >= 0", name="ck_deliveries_over_non_negative"),
        CheckConstraint("ball_in_over >= 1", name="ck_deliveries_ball_positive"),
        CheckConstraint("bat_runs >= 0", name="ck_deliveries_bat_runs_non_negative"),
        CheckConstraint("wide_runs >= 0", name="ck_deliveries_wide_runs_non_negative"),
        CheckConstraint(
            "no_ball_runs >= 0",
            name="ck_deliveries_no_ball_runs_non_negative",
        ),
        CheckConstraint("bye_runs >= 0", name="ck_deliveries_bye_runs_non_negative"),
        CheckConstraint(
            "leg_bye_runs >= 0",
            name="ck_deliveries_leg_bye_runs_non_negative",
        ),
        CheckConstraint("total_runs >= 0", name="ck_deliveries_total_runs_non_negative"),
    )

    innings_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("innings.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    over_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ball_in_over: Mapped[int] = mapped_column(Integer, nullable=False)

    striker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    non_striker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bowler_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    bat_runs: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    wide_runs: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    no_ball_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    bye_runs: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    leg_bye_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    is_legal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_free_hit: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=false(),
    )

    dismissal_type: Mapped[DismissalType | None] = mapped_column(
        Enum(
            DismissalType,
            name="dismissal_type",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=True,
    )
    dismissed_player_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    innings: Mapped[Innings] = relationship(back_populates="deliveries")
    striker: Mapped[Player] = relationship(foreign_keys=[striker_id])
    non_striker: Mapped[Player] = relationship(foreign_keys=[non_striker_id])
    bowler: Mapped[Player] = relationship(foreign_keys=[bowler_id])
    dismissed_player: Mapped[Player | None] = relationship(
        foreign_keys=[dismissed_player_id],
    )
