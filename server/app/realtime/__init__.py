"""Realtime package — Socket.IO live scoreboard synchronisation."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.realtime.socket import (
    publish_match_update as _publish_match_update,
    publish_match_update_from_innings as _publish_match_update_from_innings,
    sio,
)

logger = logging.getLogger(__name__)


def publish_match_update(match_id: uuid.UUID) -> None:
    """Post-commit live publish; never raises to mutation callers."""
    try:
        _publish_match_update(match_id)
    except Exception:
        logger.exception("Live publish failed for match %s", match_id)


def publish_match_update_from_innings(session: Session, innings_id: uuid.UUID) -> None:
    """Post-commit live publish from innings id; never raises to mutation callers."""
    try:
        _publish_match_update_from_innings(session, innings_id)
    except Exception:
        logger.exception("Live publish failed for innings %s", innings_id)


__all__ = [
    "publish_match_update",
    "publish_match_update_from_innings",
    "sio",
]
