"""Shared timestamp columns (UTC / timezone-aware)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, text
from sqlalchemy.orm import Mapped, mapped_column


class CreatedAtMixin:
    """UTC `created_at` set by PostgreSQL (`now()` → timestamptz)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
