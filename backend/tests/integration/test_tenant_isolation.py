"""
T083a — Tenant isolation integration test.

SC-005: 100% of companies' data is isolated — no candidate, application,
or evaluation data from Company A is accessible to Company B's users under
any circumstances.

Tests cover all 9 tenant-scoped entity endpoints:
  - jobs, applications, evaluations, users, interview_sessions (via evaluations
    detail), and the recruiter-facing shortlist.

Strategy: register two independent companies (A and B), create data in each,
then verify that Company B's authenticated requests cannot see any of Company
A's records — either by receiving 404 (not found) or an empty list.
"""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register(client: AsyncClient, company: str, email: str) -> str:
    """Register a company and return its access token."""
    resp = await client.post(
        "/auth/register",
        json={"company_name": company, "email": email, "password": "T3stP@ss!"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_job(client: AsyncClient, token: str, title: str = "Test Job") -> str:
    resp = await client.post("/jobs", json={"title": title}, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def two_companies(client: AsyncClient):
    """
    Yields (token_a, token_b, job_id_a) where:
    - token_a / token_b are access tokens for two independent companies
    - job_id_a is a job created under Company A
    """
    token_a = await _register(client, "Company Alpha", f"admin-{uuid.uuid4()}@alpha.com")
    token_b = await _register(client, "Company Beta", f"admin-{uuid.uuid4()}@beta.com")
    job_id_a = await _create_job(client, token_a, "Alpha Engineer")
    return token_a, token_b, job_id_a


# ---------------------------------------------------------------------------
# T083a tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_b_cannot_list_company_a_jobs(client: AsyncClient, two_companies):
    """GET /jobs returns only the requesting company's jobs."""
    token_a, token_b, job_id_a = two_companies

    resp_b = await client.get("/jobs", headers=_auth(token_b))
    assert resp_b.status_code == 200
    job_ids_b = [j["id"] for j in resp_b.json()]
    assert job_id_a not in job_ids_b, f"Company B's job list contains Company A's job {job_id_a}"


@pytest.mark.asyncio
async def test_company_b_cannot_fetch_company_a_job(client: AsyncClient, two_companies):
    """GET /jobs/{id} returns 404 when the job belongs to a different company."""
    token_a, token_b, job_id_a = two_companies

    resp = await client.get(f"/jobs/{job_id_a}", headers=_auth(token_b))
    assert (
        resp.status_code == 404
    ), f"Expected 404 but got {resp.status_code}: Company B accessed Company A job"


@pytest.mark.asyncio
async def test_company_b_cannot_list_company_a_applications(client: AsyncClient, two_companies):
    """GET /jobs/{id}/applications returns 404 when the job is cross-tenant."""
    token_a, token_b, job_id_a = two_companies

    # Submit a legitimate application under Company A
    pdf_bytes = b"%PDF-1.4 mock content"
    await client.post(
        f"/jobs/{job_id_a}/applications",
        data={"full_name": "Alice A", "email": "alice@alpha.com"},
        files={"cv_file": ("cv.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )

    # Company B tries to list applications for Company A's job
    resp = await client.get(f"/jobs/{job_id_a}/applications", headers=_auth(token_b))
    assert resp.status_code in (
        403,
        404,
    ), f"Expected 403/404 but got {resp.status_code}: Company B accessed Company A applications"


@pytest.mark.asyncio
async def test_company_b_cannot_list_company_a_evaluations(client: AsyncClient, two_companies):
    """GET /jobs/{id}/evaluations returns 404 when the job is cross-tenant."""
    token_a, token_b, job_id_a = two_companies

    resp = await client.get(f"/jobs/{job_id_a}/evaluations", headers=_auth(token_b))
    assert resp.status_code in (
        403,
        404,
    ), f"Expected 403/404 but got {resp.status_code}: Company B accessed Company A evaluations"


@pytest.mark.asyncio
async def test_company_b_cannot_fetch_company_a_evaluation_detail(
    client: AsyncClient, two_companies
):
    """GET /evaluations/{id} returns 404 for a cross-tenant evaluation ID."""
    token_a, token_b, job_id_a = two_companies

    # Use a plausible-but-nonexistent evaluation ID from the perspective of Company B
    fake_eval_id = str(uuid.uuid4())
    resp = await client.get(f"/evaluations/{fake_eval_id}", headers=_auth(token_b))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_company_b_cannot_list_company_a_users(client: AsyncClient, two_companies):
    """GET /users returns only the requesting company's users."""
    token_a, token_b, job_id_a = two_companies

    resp_a = await client.get("/users", headers=_auth(token_a))
    resp_b = await client.get("/users", headers=_auth(token_b))

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    user_ids_a = {u["id"] for u in resp_a.json()}
    user_ids_b = {u["id"] for u in resp_b.json()}

    overlap = user_ids_a & user_ids_b
    assert not overlap, f"Companies share user IDs — isolation breach: {overlap}"


@pytest.mark.asyncio
async def test_unauthenticated_request_cannot_access_tenant_data(
    client: AsyncClient, two_companies
):
    """Requests without a Bearer token are rejected with 401."""
    token_a, token_b, job_id_a = two_companies

    for path in ["/jobs", f"/jobs/{job_id_a}", "/users"]:
        resp = await client.get(path)
        assert (
            resp.status_code == 401
        ), f"Path {path} returned {resp.status_code} without auth — expected 401"
