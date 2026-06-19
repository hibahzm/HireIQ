from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CandidateProfileUpdate(BaseModel):
    full_name: str | None = None
    open_to_work: bool | None = None


class CandidateCvResponse(BaseModel):
    has_cv: bool
    cv_extraction_method: str | None = None
    embedding_truncated: bool = False
    skills: list = []
    updated_at: datetime | None = None


class OpenJobResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    company_name: str | None = None
    created_at: datetime
    already_applied: bool = False


class CandidateApplicationResponse(BaseModel):
    id: str
    job_id: str
    job_title: str | None = None
    company_name: str | None = None
    status: str
    screening_status: str
    created_at: datetime
    # Surfaced so the candidate can act on their application from their account.
    interview_token: str | None = None
    interview_token_expires_at: datetime | None = None
    feedback_token: str | None = None
    overall_score: int | None = None


class CandidateInvitation(BaseModel):
    id: str
    job_id: str
    job_title: str | None = None
    company_name: str | None = None
    status: str
    message: str | None = None
    created_at: datetime
