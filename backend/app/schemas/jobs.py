from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CreateJobRequest(BaseModel):
    title: str
    description: str | None = None


class JobResponse(BaseModel):
    id: str
    company_id: str
    title: str
    description: str | None = None
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class SetupTurnRequest(BaseModel):
    user_message: str


class SetupTurnResponse(BaseModel):
    message: str
    status: str
    criteria_draft: dict[str, Any] | None = None
