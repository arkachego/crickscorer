"""Durable batter-replacement events for state reconstruction (Phase 12).

A replacement is not a delivery. It is recorded against the wicket delivery that
created the vacant active-batter slot so reconstruction can replay history.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UuidPrimaryKeyMixin
from app.db.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from app.db.models.delivery import Delivery
    from app.db.models.innings import Innings
    from app.db.models.player import Player


class BatterReplacement(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "batter_replacements"
    __table_args__ = (
        UniqueConstraint(
            "innings_id",
            "wicket_delivery_id",
            name="uq_batter_replacements_innings_wicket",
        ),
    )

    innings_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("innings.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    wicket_delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deliveries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # True when the vacant slot was striker_id; False when non_striker_id.
    fills_striker_slot: Mapped[bool] = mapped_column(Boolean, nullable=False)

    innings: Mapped[Innings] = relationship(back_populates="batter_replacements")
    wicket_delivery: Mapped[Delivery] = relationship()
    player: Mapped[Player] = relationship()
