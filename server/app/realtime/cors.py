"""Browser-reachable CORS origins shared by Socket.IO and HTTP."""

from __future__ import annotations

import os


def browser_cors_origins() -> list[str]:
    """Origins allowed for Socket.IO and HTTP CORS.

    Defaults cover local Admin (5173) and Viewer (5174). Override with
    comma-separated ``SOCKETIO_CORS_ORIGINS``.
    """
    raw = os.environ.get("SOCKETIO_CORS_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]


# Backwards-compatible alias used by realtime Socket.IO wiring.
def socketio_cors_origins() -> list[str]:
    return browser_cors_origins()
