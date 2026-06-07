"""
T080 (US5) — Candidate feedback report endpoint integration test.

Covers acceptance scenarios for User Story 5:
  - Valid token → 200 with per-dimension scores and a written summary.
  - The hire/no-hire `recommendation` is NEVER exposed to the candidate.
  - Unknown token → 404; expired token → 410.

Not constitution-mandated (Principle VIII covers auth / screening / interview /
evaluation pipelines), but added per /speckit-analyze finding F3 to lock the
public contract of GET /feedback/{token}.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from httpx import AsyncClient


@pytest.fixture
async def client(app):
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_evaluation_with_token(
    *,
    token: str,
    expires_at: datetime,
    summary: str | None = "Strengths: Clear communicator.\nAreas for improvement: More depth on system design.",
) -> None:
    """
    Insert a self-contained company → job → candidate → application → evaluation
    chain and stamp the evaluation with a feedback token. Uses the raw session
    factory (the feedback endpoint reads by token, bypassing RLS).
    """
    from app.db import _get_session_factory

    company_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    candidate_id = str(uuid.uuid4())
    application_id = str(uuid.uuid4())
    evaluation_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    async with _get_session_factory()() as session:
        async with session.begin():
            await session.execute(
                sa.text("SET LOCAL app.current_company_id = :cid"),
                {"cid": company_id},
            )
            await session.execute(
                sa.text(
                    "INSERT INTO companies (id, name, created_at, updated_at) "
                    "VALUES (:id, :name, :now, :now)"
                ),
                {"id": company_id, "name": "Feedback Co", "now": now},
            )
            await session.execute(
                sa.text(
                    "INSERT INTO jobs (id, company_id, title, status, created_at, updated_at) "
                    "VALUES (:id, :cid, :title, 'closed', :now, :now)"
                ),
                {"id": job_id, "cid": company_id, "title": "Backend Engineer", "now": now},
            )
            await session.execute(
                sa.text(
                    "INSERT INTO candidates (id, full_name, email, created_at, updated_at) "
                    "VALUES (:id, :name, :email, :now, :now)"
                ),
                {
                    "id": candidate_id,
                    "name": "Jane Candidate",
                    "email": f"jane-{uuid.uuid4()}@example.com",
                    "now": now,
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO applications "
                    "(id, job_id, candidate_id, company_id, screening_status, status, created_at, updated_at) "
                    "VALUES (:id, :job, :cand, :cid, 'qualified', 'evaluated', :now, :now)"
                ),
                {
                    "id": application_id,
                    "job": job_id,
                    "cand": candidate_id,
                    "cid": company_id,
                    "now": now,
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO evaluations "
                    "(id, application_id, company_id, overall_score, recommendation, "
                    " dimension_scores, consistency_flags, communication_quality, "
                    " confidence_flag, confidence_reason, summary, "
                    " feedback_token, feedback_token_expires_at, created_at, updated_at) "
                    "VALUES (:id, :app, :cid, :score, :rec, "
                    " CAST(:dims AS jsonb), CAST('[]' AS jsonb), CAST(:cq AS jsonb), "
                    " false, NULL, :summary, :token, :expires, :now, :now)"
                ),
                {
                    "id": evaluation_id,
                    "app": application_id,
                    "cid": company_id,
                    "score": 78,
                    "rec": "hire",
                    "dims": '[{"dimension": "communication", "score": 82, "evidence_quotes": []}]',
                    "cq": '{"response_depth": 0.7, "filler_word_frequency": 0.05, "deflection_frequency": 0.0}',
                    "summary": summary,
                    "token": token,
                    "expires": expires_at,
                    "now": now,
                },
            )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_token_returns_report_without_recommendation(client: AsyncClient):
    """Valid token → 200; dimension scores + summary present; recommendation hidden."""
    token = str(uuid.uuid4())
    await _seed_evaluation_with_token(
        token=token, expires_at=datetime.now(timezone.utc) + timedelta(days=30)
    )

    resp = await client.get(f"/feedback/{token}")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["job_title"] == "Backend Engineer"
    assert body["overall_score"] == 78
    assert len(body["dimension_scores"]) == 1
    assert body["dimension_scores"][0]["dimension"] == "communication"
    assert body["summary"]["strengths"] == "Clear communicator."
    assert body["summary"]["areas_for_improvement"] == "More depth on system design."

    # FR/US5: hire/no-hire recommendation must never reach the candidate.
    assert "recommendation" not in body


@pytest.mark.asyncio
async def test_unknown_token_returns_404(client: AsyncClient):
    resp = await client.get(f"/feedback/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_expired_token_returns_410(client: AsyncClient):
    token = str(uuid.uuid4())
    await _seed_evaluation_with_token(
        token=token, expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )

    resp = await client.get(f"/feedback/{token}")
    assert resp.status_code == 410
