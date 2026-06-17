"""
Integration tests for company in-app sourcing + invitations (feature 018, Phase 2).

Covers the privacy/isolation guarantees and the invite→accept loop:
  * only open_to_work candidates appear (FR-016),
  * contact details are withheld pre-acceptance (FR-018),
  * accepting an invitation creates a deduplicated application (FR-020),
  * sourcing is gated by the per-job sourcing_enabled flag (FR-014).
"""

from __future__ import annotations

import uuid
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.conftest import ADMIN_URL

VEC = [0.02] * 1536


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register_company(client: AsyncClient, email: str) -> tuple[str, str]:
    reg = await client.post(
        "/auth/register",
        json={"company_name": "Acme", "email": email, "password": "S3cur3P@ss!"},
    )
    token = reg.json()["access_token"]
    me = await client.get("/auth/me", headers=_auth(token))
    return token, me.json()["company_id"]


async def _register_candidate_with_cv(
    client: AsyncClient, email: str, *, open_to_work: bool, skills: list
) -> tuple[str, str]:
    reg = await client.post(
        "/auth/candidate/register",
        json={"email": email, "full_name": "Cand " + email[:4], "password": "S3cur3P@ss!"},
    )
    token = reg.json()["access_token"]
    cid = (await client.get("/auth/candidate/me", headers=_auth(token))).json()["id"]

    with (
        patch(
            "app.services.ocr_service.OcrService.extract",
            new_callable=AsyncMock,
            return_value=("cv text", "pymupdf"),
        ),
        patch(
            "app.services.embedding_service.EmbeddingService.embed_whole_cv",
            new_callable=AsyncMock,
            return_value=(VEC, False, {"agent_type": "embedding", "model": "m", "metadata": {}}),
        ),
        # Skip the background skill-extraction call to the agents service.
        patch("app.api.routers.candidates.run_skill_extraction_background", new_callable=AsyncMock),
    ):
        await client.post(
            "/candidate/cv",
            headers=_auth(token),
            files={"cv_file": ("cv.pdf", BytesIO(b"%PDF-1.4 x"), "application/pdf")},
        )

    # Set open_to_work + structured skills directly (extraction runs async via agents).
    import json

    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                sa.text("UPDATE candidates SET open_to_work = :o WHERE id = :id"),
                {"o": open_to_work, "id": cid},
            )
            await conn.execute(
                sa.text("UPDATE candidate_cvs SET skills = CAST(:s AS jsonb) WHERE candidate_id = :id"),
                {"s": json.dumps(skills), "id": cid},
            )
    finally:
        await engine.dispose()
    return cid, token


async def _seed_sourcing_job(company_id: str, created_by: str, *, sourcing: bool) -> str:
    job_id = str(uuid.uuid4())
    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO jobs (id, company_id, title, description, status, created_by, "
                    "streaming_interview, sourcing_enabled) "
                    "VALUES (:id, :cid, 'Backend Engineer', 'Node.js backend role', 'active', "
                    ":cb, false, :src)"
                ),
                {"id": job_id, "cid": company_id, "cb": created_by, "src": sourcing},
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO job_criteria (id, job_id, company_id, required_skills, "
                    "optional_skills, experience_level, evaluation_dimensions, min_screening_score) "
                    "VALUES (:id, :jid, :cid, CAST(:req AS jsonb), CAST('[]' AS jsonb), 'senior', "
                    "CAST(:dims AS jsonb), 60)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "jid": job_id,
                    "cid": company_id,
                    "req": '["Node.js"]',
                    "dims": '[{"name": "Tech", "weight": 1.0, "description": "x"}]',
                },
            )
    finally:
        await engine.dispose()
    return job_id


def _patch_query_embedding():
    return patch(
        "app.services.embedding_service.EmbeddingService.embed_text",
        new_callable=AsyncMock,
        return_value=(VEC, {"agent_type": "embedding", "model": "m", "metadata": {}}),
    )


@pytest.mark.asyncio
async def test_sourcing_disabled_job_returns_400(client: AsyncClient):
    token, company_id = await _register_company(client, "co1@acme.com")
    user_id = (await client.get("/auth/me", headers=_auth(token))).json()["id"]
    job_id = await _seed_sourcing_job(company_id, user_id, sourcing=False)
    resp = await client.get(f"/jobs/{job_id}/sourcing", headers=_auth(token))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_search_excludes_not_open_to_work_and_hides_contact(client: AsyncClient):
    token, company_id = await _register_company(client, "co2@acme.com")
    user_id = (await client.get("/auth/me", headers=_auth(token))).json()["id"]
    job_id = await _seed_sourcing_job(company_id, user_id, sourcing=True)

    open_cid, _ = await _register_candidate_with_cv(
        client, "open@x.com", open_to_work=True, skills=[{"skill": "node.js", "years": 3.0}]
    )
    await _register_candidate_with_cv(
        client, "hidden@x.com", open_to_work=False, skills=[{"skill": "node.js", "years": 5.0}]
    )

    with _patch_query_embedding():
        resp = await client.get(f"/jobs/{job_id}/sourcing", headers=_auth(token))
    assert resp.status_code == 200
    results = resp.json()
    ids = [r["candidate_id"] for r in results]
    assert open_cid in ids
    assert all(r["candidate_id"] != "hidden" for r in results)
    # Only open-to-work candidates surface; contact details are withheld.
    assert len(ids) == 1
    assert "email" not in results[0]


@pytest.mark.asyncio
async def test_invite_then_accept_creates_deduped_application(client: AsyncClient):
    token, company_id = await _register_company(client, "co3@acme.com")
    user_id = (await client.get("/auth/me", headers=_auth(token))).json()["id"]
    job_id = await _seed_sourcing_job(company_id, user_id, sourcing=True)

    cand_id, cand_token = await _register_candidate_with_cv(
        client, "invitee@x.com", open_to_work=True, skills=[{"skill": "node.js", "years": 4.0}]
    )

    # Invite
    inv = await client.post(
        f"/jobs/{job_id}/sourcing/{cand_id}/invite", headers=_auth(token), json={}
    )
    assert inv.status_code == 201, inv.text

    # Candidate sees the pending invitation
    listing = await client.get("/candidate/invitations", headers=_auth(cand_token))
    assert listing.status_code == 200
    invitations = listing.json()
    assert len(invitations) == 1
    invitation_id = invitations[0]["id"]
    assert invitations[0]["status"] == "pending"

    # Accept → application created (screening dispatch mocked away)
    with patch(
        "app.api.routers.candidates.run_screening_background", new_callable=AsyncMock
    ):
        accept = await client.post(
            f"/candidate/invitations/{invitation_id}/accept", headers=_auth(cand_token)
        )
        assert accept.status_code == 201, accept.text
        # Accepting again is rejected.
        again = await client.post(
            f"/candidate/invitations/{invitation_id}/accept", headers=_auth(cand_token)
        )
    assert again.status_code == 409

    # The candidate now has exactly one application for the job (deduped).
    apps = (await client.get("/candidate/applications", headers=_auth(cand_token))).json()
    assert sum(1 for a in apps if a["job_id"] == job_id) == 1


@pytest.mark.asyncio
async def test_invite_not_open_to_work_candidate_422(client: AsyncClient):
    token, company_id = await _register_company(client, "co4@acme.com")
    user_id = (await client.get("/auth/me", headers=_auth(token))).json()["id"]
    job_id = await _seed_sourcing_job(company_id, user_id, sourcing=True)
    cand_id, _ = await _register_candidate_with_cv(
        client, "closed@x.com", open_to_work=False, skills=[{"skill": "node.js", "years": 3.0}]
    )
    resp = await client.post(
        f"/jobs/{job_id}/sourcing/{cand_id}/invite", headers=_auth(token), json={}
    )
    assert resp.status_code == 422
