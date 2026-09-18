"""API v1 router."""

from fastapi import APIRouter

from app.api.v1.innings import router as innings_router
from app.api.v1.matches import router as matches_router
from app.api.v1.teams import router as teams_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(teams_router)
api_v1_router.include_router(matches_router)
api_v1_router.include_router(innings_router)
