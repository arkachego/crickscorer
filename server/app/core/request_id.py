"""Request correlation ID helpers (non-persistent diagnostics)."""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id_ctx.get()


def bind_request_id(request_id: str) -> Token[str | None]:
    """Set request id and return a token for ``reset_request_id``."""
    return _request_id_ctx.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id_ctx.reset(token)


def new_request_id() -> str:
    return str(uuid.uuid4())
