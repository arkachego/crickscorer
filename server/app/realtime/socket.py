"""Socket.IO server — match rooms and authoritative live snapshots."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import socketio
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.exceptions import NotFoundError
from app.realtime.cors import socketio_cors_origins
from app.realtime.snapshot import build_match_live_snapshot

logger = logging.getLogger(__name__)

ROOM_PREFIX = "match:"

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=socketio_cors_origins(),
    logger=False,
    engineio_logger=False,
)

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store the ASGI event loop so sync mutation handlers can emit safely."""
    global _main_loop
    _main_loop = loop


def match_room(match_id: uuid.UUID | str) -> str:
    return f"{ROOM_PREFIX}{match_id}"


def _parse_match_id(raw: Any) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        return None


def _match_exists(session: Session, match_id: uuid.UUID) -> bool:
    from app.db.models import Match

    return session.get(Match, match_id) is not None


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: Any = None) -> bool:
    return True


@sio.event
async def disconnect(sid: str) -> None:
    return None


@sio.on("match:join")
async def match_join(sid: str, data: Any = None) -> None:
    payload = data if isinstance(data, dict) else {}
    match_id = _parse_match_id(payload.get("match_id"))
    if match_id is None:
        logger.info("Socket join rejected sid=%s reason=INVALID_MATCH_ID", sid)
        await sio.emit(
            "match:error",
            {"code": "INVALID_MATCH_ID", "message": "match_id must be a valid UUID."},
            to=sid,
        )
        return

    session = SessionLocal()
    try:
        if not _match_exists(session, match_id):
            logger.info(
                "Socket join rejected sid=%s match_id=%s reason=MATCH_NOT_FOUND",
                sid,
                match_id,
            )
            await sio.emit(
                "match:error",
                {"code": "MATCH_NOT_FOUND", "message": "Match was not found."},
                to=sid,
            )
            return
        snapshot = build_match_live_snapshot(session, match_id, bump=False)
    except NotFoundError:
        logger.info(
            "Socket join rejected sid=%s match_id=%s reason=MATCH_NOT_FOUND",
            sid,
            match_id,
        )
        await sio.emit(
            "match:error",
            {"code": "MATCH_NOT_FOUND", "message": "Match was not found."},
            to=sid,
        )
        return
    except Exception:
        logger.exception("Socket join failed sid=%s match_id=%s", sid, match_id)
        await sio.emit(
            "match:error",
            {
                "code": "JOIN_FAILED",
                "message": "Unable to join the match room. Please try again.",
            },
            to=sid,
        )
        return
    finally:
        session.close()

    # Leave any prior match rooms for this socket, then join the requested room.
    for room in list(sio.rooms(sid)):
        if room != sid and str(room).startswith(ROOM_PREFIX):
            await sio.leave_room(sid, room)

    await sio.enter_room(sid, match_room(match_id))
    await sio.emit("match:joined", snapshot, to=sid)


async def _emit_match_update(snapshot: dict[str, Any]) -> None:
    room = match_room(snapshot["match_id"])
    await sio.emit("match:update", snapshot, room=room)


def publish_match_update(match_id: uuid.UUID) -> None:
    """Build and broadcast ``match:update`` after a successful DB commit.

    Safe to call from sync FastAPI route/threadpool code. Uses the ASGI
    event loop captured at startup via ``run_coroutine_threadsafe``.

    Never raises — a live-event failure must not undo a committed mutation.
    """
    try:
        session = SessionLocal()
        try:
            snapshot = build_match_live_snapshot(session, match_id, bump=True)
        finally:
            session.close()

        loop = _main_loop
        if loop is None or not loop.is_running():
            logger.warning(
                "Socket.IO loop unavailable; skipped match:update for %s", match_id
            )
            return

        fut = asyncio.run_coroutine_threadsafe(_emit_match_update(snapshot), loop)
        fut.result(timeout=5)
    except Exception:
        logger.exception("Failed to emit match:update for %s", match_id)


def publish_match_update_from_innings(session: Session, innings_id: uuid.UUID) -> None:
    """Resolve match_id from an innings row and publish (post-commit). Never raises."""
    from app.db.models import Innings

    try:
        fresh = SessionLocal()
        try:
            innings = fresh.get(Innings, innings_id)
            if innings is None:
                logger.warning("Cannot publish update; innings %s missing", innings_id)
                return
            match_id = innings.match_id
        finally:
            fresh.close()
        publish_match_update(match_id)
    except Exception:
        logger.exception(
            "Failed to publish match update from innings %s", innings_id
        )
