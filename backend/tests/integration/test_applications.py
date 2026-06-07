"""
Additional application endpoint integration tests (part of T039 set).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.fixture
async def client(app):
    async with AsyncClient(app=app, base_url="http://test") as c:
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
async def test_application_rejects_non_pdf(client: AsyncClient, active_job):
    """Non-PDF files are rejected with 422."""
    job_id = active_job

    resp = await client.post(
        f"/jobs/{job_id}/applications",
        data={"full_name": "Word User", "email": "word@test.com"},
        files={"cv_file": ("cv.docx", b"PK mock docx content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 422
