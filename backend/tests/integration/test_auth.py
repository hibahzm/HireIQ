"""
Integration tests for auth endpoints.
These tests MUST be written first (constitution Principle VIII) and confirmed
failing before implementing AuthService / auth router (T026/T027).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# T021 — Company registration + admin user creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_company_returns_201_with_token(client: AsyncClient):
    """POST /auth/register creates a company + admin user, returns access token."""
    resp = await client.post(
        "/auth/register",
        json={
            "company_name": "Acme Corp",
            "email": "admin@acme.com",
            "password": "S3cur3P@ssw0rd!",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"

    # Refresh cookie must be set
    assert "refresh_token" in resp.cookies


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient):
    """Registering the same email twice returns 409."""
    payload = {
        "company_name": "Dupes Inc",
        "email": "dup@dupes.com",
        "password": "S3cur3P@ssw0rd!",
    }
    r1 = await client.post("/auth/register", json=payload)
    assert r1.status_code == 201

    r2 = await client.post("/auth/register", json=payload)
    assert r2.status_code == 409


# ---------------------------------------------------------------------------
# T022 — Login → access token valid → refresh → old token rejected → logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_token_lifecycle(client: AsyncClient):
    """
    1. Register
    2. Login → get access token + refresh cookie
    3. Access /auth/me with token → 200
    4. POST /auth/refresh → new access token returned
    5. Old access token is still valid within its 15-min window (rotation only affects refresh)
    6. POST /auth/logout → refresh token invalidated
    7. POST /auth/refresh with old cookie → 401
    """
    # 1. Register
    reg = await client.post(
        "/auth/register",
        json={
            "company_name": "Token Corp",
            "email": "token@corp.com",
            "password": "S3cur3P@ssw0rd!",
        },
    )
    assert reg.status_code == 201

    # 2. Login
    login_resp = await client.post(
        "/auth/login",
        json={"email": "token@corp.com", "password": "S3cur3P@ssw0rd!"},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]
    assert "refresh_token" in login_resp.cookies

    # 3. Verify access token works
    me_resp = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200

    # 4. Refresh — new access token issued
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    new_access_token = refresh_resp.json()["access_token"]
    assert new_access_token != access_token
    # New refresh cookie set (rotation)
    assert "refresh_token" in refresh_resp.cookies

    # 5. Logout
    logout_resp = await client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {new_access_token}"}
    )
    assert logout_resp.status_code == 204

    # 6. Old refresh cookie should now be rejected
    stale_refresh = await client.post("/auth/refresh")
    assert stale_refresh.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={
            "company_name": "Auth Co",
            "email": "user@authco.com",
            "password": "CorrectPass123!",
        },
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "user@authco.com", "password": "WrongPass999"},
    )
    assert resp.status_code == 401
