from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ApplicationResponse(BaseModel):
    id: str
    job_id: str
    candidate_id: str
    company_id: str
    cv_blob_key: str
    cv_text: str | None
    cv_extraction_method: str | None
    screening_score: int | None
    screening_rationale: str | None
    screening_status: str
    interview_token: str | None
    interview_token_expires_at: datetime | None
    status: str
    created_at: datetime
    updated_at: datetime
