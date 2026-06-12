"""
Additional application endpoint integration tests (part of T039 set).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_application_form_validates_file_size(client: AsyncClient, active_job):
    """Files larger than 10 MB are rejected with 413."""
    job_id = active_job
    large_file = b"0" * (10 * 1024 * 1024 + 1)

    resp = await client.post(
        f"/jobs/{job_id}/applications",
        data={"full_name": "Big Bob", "email": "bigbob@test.com"},
        files={"cv_file": ("large.pdf", large_file, "application/pdf")},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_application_rejects_unsupported_type(client: AsyncClient, active_job):
    """Unsupported file types (e.g. .txt) are rejected with 422.

    NOTE: As of V2-1, DOCX and image CVs are accepted — see test_cv_formats.py.
    """
    job_id = active_job

    resp = await client.post(
        f"/jobs/{job_id}/applications",
        data={"full_name": "Terry Text", "email": "terry@test.com"},
        files={"cv_file": ("cv.txt", b"plain text, not a CV file", "text/plain")},
    )
    assert resp.status_code == 422
