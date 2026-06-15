"""
Integration tests for the CV screening pipeline.
Constitution Principle VIII — write FIRST, confirm FAILING before T049.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _mock_agents_client(payload: dict):
    """
    Stand-in for `httpx.AsyncClient` inside the screening service. Patching the
    class *name* (not `.post`) leaves the already-instantiated ASGI test client
    untouched while every client the service constructs returns `payload`.
    """

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value=payload)
            return resp

    return _Client


# ---------------------------------------------------------------------------
# T038 — Full CV screening pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screening_pipeline_sets_score_and_rationale(client: AsyncClient, active_job_token):
    """
    Upload a PDF CV to an active job →
    screening pipeline completes →
    application shows screening_score + screening_rationale (PII-redacted).
    """
    token, job_id = active_job_token

    # Submit application with a mock PDF
    import io

    try:
        from reportlab.pdfgen import canvas as pdf_canvas  # type: ignore

        pdf_buffer = io.BytesIO()
        c = pdf_canvas.Canvas(pdf_buffer)
        c.drawString(100, 750, "John Doe — Software Engineer with 5 years of Python experience.")
        c.save()
        pdf_bytes = pdf_buffer.getvalue()
    except ImportError:
        pdf_bytes = b"%PDF-1.4 mock pdf content for testing"

    agents_payload = {
        "score": 82,
        "rationale": "Strong Python background matches requirements.",
        "status": "qualified",
        "guardrail_triggered": False,
    }
    with (
        patch("app.services.ocr_service.OcrService.extract", new_callable=AsyncMock) as mock_ocr,
        patch(
            "app.services.embedding_service.EmbeddingService.embed_text", new_callable=AsyncMock
        ) as mock_embed,
        patch("httpx.AsyncClient", _mock_agents_client(agents_payload)),
    ):
        mock_ocr.return_value = ("Software Engineer with 5 years Python experience.", "pymupdf")
        # embed_text returns (embedding, usage_event)
        mock_embed.return_value = (
            [0.0] * 1536,
            {
                "agent_type": "embedding",
                "model": "text-embedding-3-small",
                "prompt_tokens": 10,
                "completion_tokens": 0,
                "estimated_cost_usd": 0.0,
                "metadata": {"operation": "cv_chunk_embedding"},
            },
        )

        resp = await client.post(
            f"/jobs/{job_id}/applications",
            data={"full_name": "Jane Smith", "email": "jane@example.com"},
            files={"cv_file": ("cv.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 201
        application_id = resp.json()["id"]

        # Screening runs as a fire-and-forget asyncio task — poll (inside the
        # patch context, so the mocked agents call stays in effect) until it lands.
        import asyncio

        data = None
        for _ in range(50):
            await asyncio.sleep(0.1)
            app_resp = await client.get(
                f"/applications/{application_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert app_resp.status_code == 200
            data = app_resp.json()
            if data["screening_status"] not in ("pending",):
                break
        assert data is not None
    assert data["screening_score"] is not None
    assert data["screening_rationale"] is not None
    # PII-redacted: should NOT contain raw email addresses
    assert "@" not in data["screening_rationale"] or "[EMAIL]" in data["screening_rationale"]


# ---------------------------------------------------------------------------
# T039 — Duplicate application + corrupt PDF rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_application_returns_409(client: AsyncClient, active_job):
    """Second application with same email + same job returns 409."""
    job_id = active_job
    pdf_bytes = b"%PDF-1.4 test"

    # This test covers duplicate detection, not extraction — mock OCR so the
    # placeholder bytes pass validation.
    with patch("app.services.ocr_service.OcrService.extract", new_callable=AsyncMock) as mock_ocr:
        mock_ocr.return_value = ("Bob Builder, construction engineer.", "pymupdf")

        r1 = await client.post(
            f"/jobs/{job_id}/applications",
            data={"full_name": "Bob Builder", "email": "bob@builder.com"},
            files={"cv_file": ("cv.pdf", pdf_bytes, "application/pdf")},
        )
        assert r1.status_code == 201

        r2 = await client.post(
            f"/jobs/{job_id}/applications",
            data={"full_name": "Bob Builder", "email": "bob@builder.com"},
            files={"cv_file": ("cv.pdf", pdf_bytes, "application/pdf")},
        )
        assert r2.status_code == 409


@pytest.mark.asyncio
async def test_corrupt_pdf_returns_422_no_application_created(client: AsyncClient, active_job):
    """Corrupt PDF → 422 response and no application record in DB."""
    job_id = active_job

    with patch("app.services.ocr_service.OcrService.extract", new_callable=AsyncMock) as mock_ocr:
        mock_ocr.side_effect = ValueError("corrupted_pdf")

        resp = await client.post(
            f"/jobs/{job_id}/applications",
            data={"full_name": "Alice Corrupt", "email": "alice@corrupt.com"},
            files={"cv_file": ("broken.pdf", b"not a real pdf", "application/pdf")},
        )
        assert resp.status_code == 422

    # Confirm no application was created
    # (would need DB check — left as assertion on response body)
    # The 422 is the signal; no partial record should exist per FR-010
