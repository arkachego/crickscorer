"""Authoritative match snapshot for Socket.IO transport."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.realtime.versions import bump_match_version, current_match_version
from app.services.matches import get_match, serialize_match
from app.services.scoring import list_innings_deliveries


def build_match_live_snapshot(
    session: Session,
    match_id: uuid.UUID,
    *,
    bump: bool,
) -> dict[str, Any]:
    """Build JSON-serialisable live snapshot for join/update events."""
    match = get_match(session, match_id)
    match_payload = serialize_match(match, session)
    deliveries_by_innings: dict[str, list[dict[str, Any]]] = {}
    for innings in match.innings:
        items = list_innings_deliveries(session, innings.id)
        deliveries_by_innings[str(innings.id)] = [
            item.model_dump(mode="json") for item in items
        ]

    version = bump_match_version(match_id) if bump else current_match_version(match_id)
    return {
        "match_id": str(match_id),
        "version": version,
        "match": match_payload.model_dump(mode="json"),
        "deliveries_by_innings": deliveries_by_innings,
    }
