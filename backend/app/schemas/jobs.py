from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    title: str
    description: str | None = None
    streaming_interview: bool = True


class JobResponse(BaseModel):
    id: str
    company_id: str
    title: str
    description: str | None = None
    streaming_interview: bool
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
    job_status: str | None = None


class JobCriteriaRequest(BaseModel):
    required_skills: list[dict[str, Any]] = Field(default_factory=list)
    optional_skills: list[dict[str, Any]] = Field(default_factory=list)
    experience_level: str = "mid"
    min_years_experience: int | None = None
    evaluation_dimensions: list[dict[str, Any]]
    dealbreakers: list[dict[str, Any]] = Field(default_factory=list)
    min_screening_score: int = 60
