"""Team list schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    short_code: str
    flag_url: str


class PlayerResponse(BaseModel):
    """Roster person for Admin selectors (roles + batting_order eligibility)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    team_id: uuid.UUID
    name: str
    batting_order: int | None = None
    roles: list[str] = Field(default_factory=list)
