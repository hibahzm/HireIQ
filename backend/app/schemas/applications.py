from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ApplicationResponse(BaseModel):
    id: str
    job_id: str
    candidate_id: str
    company_id: str
    cv_blob_key: str
    # These are nullable AND have no DB default, so a freshly-created Application's
    # __dict__ omits them entirely (they're only populated on a re-SELECT). Default
    # them to None so ApplicationResponse(**application.__dict__) doesn't raise a
    # missing-field error on the create path (the 500 on application submit).
    cv_text: str | None = None
    cv_extraction_method: str | None = None
    screening_score: int | None = None
    screening_rationale: str | None = None
    screening_status: str = "pending"
    interview_token: str | None = None
    interview_token_expires_at: datetime | None = None
    evaluation_id: str | None = None
    status: str = "applied"
    created_at: datetime
    updated_at: datetime
