from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.schemas.applications import ApplicationResponse


def test_application_response_accepts_uuid_identifiers() -> None:
    response = ApplicationResponse(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        job_id=UUID("00000000-0000-0000-0000-000000000002"),
        candidate_id=UUID("6744e05f-ed1b-432a-8020-d27d38e60223"),
        company_id=UUID("00000000-0000-0000-0000-000000000003"),
        cv_blob_key="cvs/job/cv.pdf",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    assert response.candidate_id == "6744e05f-ed1b-432a-8020-d27d38e60223"
    assert response.model_dump(mode="json")["candidate_id"] == (
        "6744e05f-ed1b-432a-8020-d27d38e60223"
    )
