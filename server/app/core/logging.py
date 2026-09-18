"""Application logging configuration."""

from __future__ import annotations

import logging
import sys

from app.core.request_id import get_request_id


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"  # type: ignore[attr-defined]
        return True


def configure_logging() -> None:
    """Configure process logging once (idempotent)."""
    root = logging.getLogger()
    if getattr(root, "_crickscorer_configured", False):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [request_id=%(request_id)s] "
            "%(name)s: %(message)s"
        )
    )
    handler.addFilter(RequestIdFilter())

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Quiet noisy libraries; keep app + uvicorn access useful.
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("engineio.server").setLevel(logging.WARNING)
    logging.getLogger("socketio.server").setLevel(logging.WARNING)

    setattr(root, "_crickscorer_configured", True)
