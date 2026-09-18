"""CrickScorer FastAPI application entry point with Socket.IO ASGI mount."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api import api_v1_router
from app.core.logging import configure_logging
from app.core.request_id import (
    bind_request_id,
    get_request_id,
    new_request_id,
    reset_request_id,
)
from app.exceptions import AppError
from app.realtime.cors import browser_cors_origins
from app.realtime.socket import set_main_loop, sio

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Propagate or generate X-Request-ID for diagnostics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get("x-request-id", "").strip()
        request_id = incoming if incoming and len(incoming) <= 128 else new_request_id()
        token = bind_request_id(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers["X-Request-ID"] = request_id
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    set_main_loop(asyncio.get_running_loop())
    logger.info("CrickScorer API started")
    yield
    logger.info("CrickScorer API shutting down")


fastapi_app = FastAPI(
    title="CrickScorer",
    version="0.20.0",
    description="Cricket live-scoring backend",
    lifespan=lifespan,
)

# CORS allowlist mirrors Socket.IO (Vite proxy is primary; direct browser access
# to :8000 is supported for the same local Admin/Viewer origins).
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=browser_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
fastapi_app.add_middleware(RequestIdMiddleware)
fastapi_app.include_router(api_v1_router)


def _error_body(code: str, message: str) -> dict:
    return {"detail": {"code": code, "message": message}}


@fastapi_app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.info(
        "AppError %s status=%s path=%s request_id=%s message=%s",
        exc.code,
        exc.status_code,
        request.url.path,
        get_request_id(),
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message),
    )


@fastapi_app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.info(
        "Request validation failed path=%s request_id=%s",
        request.url.path,
        get_request_id(),
    )
    # Preserve FastAPI's detailed validation body for 422 clients.
    # ctx may contain Exception instances that are not JSON-serializable.
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(
                exc.errors(),
                custom_encoder={Exception: lambda e: str(e) or repr(e)},
            )
        },
    )


@fastapi_app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning(
        "IntegrityError path=%s request_id=%s",
        request.url.path,
        get_request_id(),
        exc_info=exc,
    )
    return JSONResponse(
        status_code=409,
        content=_error_body(
            "DATA_CONFLICT",
            "The request conflicts with persisted data. Refresh and try again.",
        ),
    )


@fastapi_app.exception_handler(OperationalError)
async def operational_error_handler(
    request: Request, exc: OperationalError
) -> JSONResponse:
    logger.error(
        "OperationalError path=%s request_id=%s",
        request.url.path,
        get_request_id(),
        exc_info=exc,
    )
    return JSONResponse(
        status_code=503,
        content=_error_body(
            "DATABASE_UNAVAILABLE",
            "The database is temporarily unavailable. Please try again shortly.",
        ),
    )


@fastapi_app.exception_handler(DBAPIError)
async def dbapi_error_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    logger.error(
        "DBAPIError path=%s request_id=%s",
        request.url.path,
        get_request_id(),
        exc_info=exc,
    )
    return JSONResponse(
        status_code=503,
        content=_error_body(
            "DATABASE_ERROR",
            "A database error occurred. Please try again.",
        ),
    )


@fastapi_app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.error(
        "SQLAlchemyError path=%s request_id=%s",
        request.url.path,
        get_request_id(),
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content=_error_body(
            "DATABASE_ERROR",
            "A database error occurred. Please try again.",
        ),
    )


@fastapi_app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception path=%s request_id=%s",
        request.url.path,
        get_request_id(),
    )
    return JSONResponse(
        status_code=500,
        content=_error_body(
            "INTERNAL_SERVER_ERROR",
            "An unexpected server error occurred.",
        ),
    )


@fastapi_app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness probe for Docker Compose and local checks (no DB dependency)."""
    return {"status": "ok"}


# Compose Socket.IO with FastAPI on a single ASGI app (path /socket.io/).
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
