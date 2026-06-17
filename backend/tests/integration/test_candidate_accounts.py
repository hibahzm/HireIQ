"""
Integration tests for candidate accounts + one-click apply (feature 018, Phase 1).

Constitution Principle VIII (NON-NEGOTIABLE) domains covered here:
  * candidate auth + token-type isolation (security boundary),
  * whole-CV single-embedding upload,
  * one-click apply with cross-route email dedup.
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


CAND = {"email": "seeker@example.com", "full_name": "Sam Seeker", "password": "S3cur3P@ss!"}


async def _register_candidate(client: AsyncClient, **overrides) -> str:
    body = {**CAND, **overrides}
    resp = await client.post("/auth/candidate/register", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cv_upload():
    return {"cv_file": ("cv.pdf", BytesIO(b"%PDF-1.4 fake"), "application/pdf")}


def _patch_cv_processing():
    """Mock OCR + whole-CV embedding so uploads don't hit external services."""
    return (
        patch(
            "app.services.ocr_service.OcrService.extract",
            new_callable=AsyncMock,
            return_value=("Node.js engineer with 3 years experience", "pymupdf"),
        ),
        patch(
            "app.services.embedding_service.EmbeddingService.embed_whole_cv",
            new_callable=AsyncMock,
            return_value=(
                [0.01] * 1536,
                False,
                {
                    "agent_type": "embedding",
                    "model": "text-embedding-3-small",
                    "prompt_tokens": 12,
                    "completion_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "metadata": {"operation": "candidate_cv_embedding", "original_tokens": 12},
                },
            ),
        ),
    )


# ── registration / dedup ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_candidate_register_returns_token_and_cookie(client: AsyncClient):
    resp = await client.post("/auth/candidate/register", json=CAND)
    assert resp.status_code == 201
    assert "access_token" in resp.json()
    assert "refresh_token" in resp.cookies


@pytest.mark.asyncio
async def test_candidate_register_duplicate_email_409(client: AsyncClient):
    await _register_candidate(client)
    resp = await client.post("/auth/candidate/register", json=CAND)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_candidate_cannot_reuse_company_email(client: AsyncClient):
    """Email is globally unique across company users and candidates."""
    await client.post(
        "/auth/register",
        json={"company_name": "Acme", "email": "taken@x.com", "password": "S3cur3P@ss!"},
    )
    resp = await client.post(
        "/auth/candidate/register",
        json={"email": "taken@x.com", "full_name": "X", "password": "S3cur3P@ss!"},
    )
    assert resp.status_code == 409


# ── token-type isolation (security boundary) ─────────────────────────────────


@pytest.mark.asyncio
async def test_candidate_token_rejected_on_company_route(client: AsyncClient):
    token = await _register_candidate(client)
    resp = await client.get("/auth/me", headers=_auth(token))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_company_token_rejected_on_candidate_route(client: AsyncClient):
    reg = await client.post(
        "/auth/register",
        json={"company_name": "Acme", "email": "boss@acme.com", "password": "S3cur3P@ss!"},
    )
    company_token = reg.json()["access_token"]
    resp = await client.get("/auth/candidate/me", headers=_auth(company_token))
    assert resp.status_code == 401


# ── CV upload (single whole-CV embedding) ────────────────────────────────────


@pytest.mark.asyncio
async def test_cv_upload_creates_profile_cv(client: AsyncClient):
    token = await _register_candidate(client)
    p_ocr, p_embed = _patch_cv_processing()
    with p_ocr, p_embed:
        resp = await client.post("/candidate/cv", headers=_auth(token), files=_cv_upload())
    assert resp.status_code == 201, resp.text
    assert resp.json()["has_cv"] is True

    me = await client.get("/auth/candidate/me", headers=_auth(token))
    assert me.json()["has_cv"] is True


@pytest.mark.asyncio
async def test_open_to_work_toggle(client: AsyncClient):
    token = await _register_candidate(client)
    resp = await client.patch("/candidate/me", headers=_auth(token), json={"open_to_work": True})
    assert resp.status_code == 200
    assert resp.json()["open_to_work"] is True


# ── one-click apply + dedup ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_one_click_apply_then_duplicate_409(client: AsyncClient, active_job: str):
    token = await _register_candidate(client)
    p_ocr, p_embed = _patch_cv_processing()
    with p_ocr, p_embed:
        await client.post("/candidate/cv", headers=_auth(token), files=_cv_upload())

    with patch("app.api.routers.candidates.run_screening_background", new_callable=AsyncMock):
        first = await client.post(f"/candidate/jobs/{active_job}/apply", headers=_auth(token))
        assert first.status_code == 201, first.text
        second = await client.post(f"/candidate/jobs/{active_job}/apply", headers=_auth(token))
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_apply_without_cv_422(client: AsyncClient, active_job: str):
    token = await _register_candidate(client)
    with patch("app.api.routers.candidates.run_screening_background", new_callable=AsyncMock):
        resp = await client.post(f"/candidate/jobs/{active_job}/apply", headers=_auth(token))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_account_apply_blocked_after_external_same_email(
    client: AsyncClient, active_job: str
):
    """External apply (public route) then account apply with the SAME email → dedup 409."""
    # External application via the public endpoint, same email as the account.
    with (
        patch(
            "app.services.ocr_service.OcrService.extract",
            new_callable=AsyncMock,
            return_value=("ext cv", "pymupdf"),
        ),
        patch("app.api.routers.applications.run_screening_background", new_callable=AsyncMock),
    ):
        ext = await client.post(
            f"/jobs/{active_job}/applications",
            data={"full_name": CAND["full_name"], "email": CAND["email"]},
            files={"cv_file": ("cv.pdf", BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )
        assert ext.status_code == 201, ext.text

    token = await _register_candidate(client)
    p_ocr, p_embed = _patch_cv_processing()
    with p_ocr, p_embed:
        await client.post("/candidate/cv", headers=_auth(token), files=_cv_upload())
    with patch("app.api.routers.candidates.run_screening_background", new_callable=AsyncMock):
        resp = await client.post(f"/candidate/jobs/{active_job}/apply", headers=_auth(token))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_browse_open_jobs_lists_active(client: AsyncClient, active_job: str):
    token = await _register_candidate(client)
    resp = await client.get("/candidate/jobs", headers=_auth(token))
    assert resp.status_code == 200
    ids = [j["id"] for j in resp.json()]
    assert active_job in ids
