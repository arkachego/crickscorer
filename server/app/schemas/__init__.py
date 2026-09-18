"""API schemas package."""

from app.schemas.match import (
    ErrorDetail,
    ErrorResponse,
    MatchCreateRequest,
    MatchResponse,
    TeamSummary,
)

__all__ = [
    "ErrorDetail",
    "ErrorResponse",
    "MatchCreateRequest",
    "MatchResponse",
    "TeamSummary",
]
