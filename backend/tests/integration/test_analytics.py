"""
Integration tests for the analytics dashboard (V2-2).

Analytics is not a Constitution-VIII TDD-mandated domain, but these are required
feature-level quality gates: accuracy (SC-001/003), ÷0 edge cases, tenant isolation
(FR-007), and authz. They follow the mocking style of test_screening.py — the
OCR/embedding/agents boundaries are mocked so screening can drive funnel state.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _agents_client(payload: dict):
    """Replacement for the `httpx.AsyncClient` *name*: patching `.post` would also
    hijack the ASGI test client (it is an httpx.AsyncClient too)."""
    from unittest.mock import MagicMock

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


def _screening_mocks():
    """Context managers that make a submitted CV screen as 'qualified'."""
    return (
        patch("app.services.ocr_service.OcrService.extract", new_callable=AsyncMock),
        patch("app.services.embedding_service.EmbeddingService.embed_text", new_callable=AsyncMock),
        patch(
            "httpx.AsyncClient",
            _agents_client({
                "score": 80, "rationale": "Good match.", "status": "qualified",
                "guardrail_triggered": False,
            }),
        ),
    )


# ---------------------------------------------------------------------------
# T007 — per-job analytics accuracy + zero-application edge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_analytics_zero_applications_edge(client: AsyncClient, active_job_token):
    """A job with no applications returns zeroed funnel and null rates — no ÷0 error."""
    token, job_id = active_job_token

    resp = await client.get(
        f"/jobs/{job_id}/analytics", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["funnel"] == {"received": 0, "qualified": 0, "interviewed": 0, "evaluated": 0}
    assert data["qualification_rate"] is None
    assert data["interview_completion_rate"] is None
    assert data["avg_evaluation_score"] is None
    assert data["time_to_screen_seconds"] is None
    assert data["time_to_evaluate_seconds"] is None
    # Distribution always returns all five bands, zero-filled.
    assert [b["band"] for b in data["score_distribution"]] == [
        "0-20", "21-40", "41-60", "61-80", "81-100"
    ]
    assert all(b["count"] == 0 for b in data["score_distribution"])


@pytest.mark.asyncio
async def test_job_analytics_funnel_accuracy(client: AsyncClient, active_job_token):
    """received/qualified counts match the applications submitted (SC-001)."""
    token, job_id = active_job_token
    ocr_cm, embed_cm, agents_cm = _screening_mocks()

    with ocr_cm as mock_ocr, embed_cm as mock_embed, agents_cm:
        mock_ocr.return_value = ("Python engineer, 5 years experience.", "pymupdf")
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
        for i in range(3):
            r = await client.post(
                f"/jobs/{job_id}/applications",
                data={"full_name": f"Cand {i}", "email": f"cand{i}@example.com"},
                files={"cv_file": ("cv.pdf", b"%PDF-1.4 test", "application/pdf")},
            )
            assert r.status_code == 201

        # Screening runs as fire-and-forget tasks — wait (inside the patch
        # context) until all three reach 'qualified'.
        import asyncio

        for _ in range(50):
            await asyncio.sleep(0.1)
            resp = await client.get(
                f"/jobs/{job_id}/analytics", headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 200
            if resp.json()["funnel"]["qualified"] == 3:
                break

    funnel = resp.json()["funnel"]
    assert funnel["received"] == 3
    # All three screened as qualified → qualification_rate == 1.0
    assert resp.json()["qualification_rate"] == 1.0


# ---------------------------------------------------------------------------
# T008 — tenant isolation (FR-007)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_analytics_tenant_isolation(client: AsyncClient):
    """Company B cannot read company A's job analytics — returns 404, no leakage."""
    # Company A registers and creates an active job.
    a = await client.post("/auth/register", json={
        "company_name": f"CompA-{uuid.uuid4().hex[:8]}",
        "email": f"a-{uuid.uuid4().hex[:8]}@ex.com", "password": "Sup3rSecret!",
    })
    assert a.status_code in (200, 201)
    token_a = a.json()["access_token"]
    job = await client.post("/jobs", json={"title": "Backend Eng"},
                            headers={"Authorization": f"Bearer {token_a}"})
    job_id = job.json()["id"]

    # Company B registers.
    b = await client.post("/auth/register", json={
        "company_name": f"CompB-{uuid.uuid4().hex[:8]}",
        "email": f"b-{uuid.uuid4().hex[:8]}@ex.com", "password": "Sup3rSecret!",
    })
    token_b = b.json()["access_token"]

    # B requesting A's job analytics is invisible across tenants.
    resp = await client.get(
        f"/jobs/{job_id}/analytics", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T014 — company overview accuracy + edge + authz
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_company_overview_structure_and_edge(client: AsyncClient, active_job_token):
    """Overview returns period + KPIs + jobs; zero-eval period yields null avg score."""
    token, _ = active_job_token

    resp = await client.get(
        "/analytics/overview", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["period"]) == 7 and data["period"][4] == "-"  # "YYYY-MM"
    assert isinstance(data["total_applications"], int)
    assert isinstance(data["jobs"], list)
    # No evaluations yet → avg score is null (no ÷0 / no error).
    assert data["avg_evaluation_score"] is None


@pytest.mark.asyncio
async def test_company_overview_requires_auth(client: AsyncClient):
    """No token → 401."""
    resp = await client.get("/analytics/overview")
    assert resp.status_code == 401
