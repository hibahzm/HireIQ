"""
Integration-test harness (closes KNOWN_GAPS.md #1).

Provides the previously-missing fixtures the integration suite references:
  - ``app``                          — a FastAPI app built with ENV=test
  - ``active_job``                   — job_id of an active job (with criteria)
  - ``active_job_token``             — (admin access token, job_id) for that job
  - ``completed_interview_session``  — (session_id, company_id, application_id)
  - ``interview_token``              — a valid interview token (str)

Design (per the gap spec):
  * Migrations run via Alembic as the **admin/superuser** role (CREATE EXTENSION
    vector + FORCE ROW LEVEL SECURITY require it).
  * The **app** connects as a separate **non-superuser** role so RLS policies are
    actually enforced — otherwise ``test_tenant_isolation.py`` (SC-005) would
    silently pass against a superuser that bypasses RLS.
  * Tables are truncated between tests for isolation.

Requirements (cannot be validated in an env without pgvector — see KNOWN_GAPS #1):
  A running pgvector Postgres. Override connection via env vars if needed:
    TEST_DATABASE_URL      admin/superuser URL (default: dev-compose creds, DB ``hireiq_test``)
    TEST_APP_DATABASE_URL  non-superuser app URL (default: role ``hireiq_test_app``)
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import bcrypt
import pytest
import sqlalchemy as sa
from jose import jwt
from sqlalchemy.ext.asyncio import create_async_engine

# ── Connection configuration ────────────────────────────────────────────────

_PGHOST = os.environ.get("PGHOST", "localhost")
_PGPORT = os.environ.get("PGPORT", "5432")
_TEST_DB = os.environ.get("TEST_DB_NAME", "hireiq_test")
_ADMIN_USER = os.environ.get("TEST_DB_ADMIN_USER", "hireiq")
_ADMIN_PASS = os.environ.get("TEST_DB_ADMIN_PASSWORD", "hireiq_dev")
_APP_USER = os.environ.get("TEST_DB_APP_USER", "hireiq_test_app")
_APP_PASS = os.environ.get("TEST_DB_APP_PASSWORD", "app_test_pw")

ADMIN_URL = os.environ.get(
    "TEST_DATABASE_URL",
    f"postgresql+asyncpg://{_ADMIN_USER}:{_ADMIN_PASS}@{_PGHOST}:{_PGPORT}/{_TEST_DB}",
)
APP_URL = os.environ.get(
    "TEST_APP_DATABASE_URL",
    f"postgresql+asyncpg://{_APP_USER}:{_APP_PASS}@{_PGHOST}:{_PGPORT}/{_TEST_DB}",
)

# The application (and everything that imports app.config) must run as the
# non-superuser role and in test mode. Set this *before* app modules import.
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = APP_URL
# backend/storage is often root-owned (created by the Docker volume) — store
# test blobs somewhere always writable instead.
os.environ.setdefault("STORAGE_LOCAL_PATH", "/tmp/hireiq-test-storage")

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _maintenance_url(async_admin_url: str, dbname: str) -> str:
    """Swap the database name (used to create the test DB from a maintenance DB)."""
    parsed = urlparse(async_admin_url.replace("+asyncpg", ""))
    return urlunparse(parsed._replace(path=f"/{dbname}"))


# ── Async admin helpers (superuser — bypasses RLS) ──────────────────────────


async def _ensure_database() -> None:
    """Create the test database if it doesn't exist (connect to a maintenance DB)."""
    import asyncpg

    maint = _maintenance_url(ADMIN_URL, os.environ.get("TEST_DB_MAINTENANCE", _ADMIN_USER))
    conn = await asyncpg.connect(maint)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", _TEST_DB)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{_TEST_DB}"')
    finally:
        await conn.close()


async def _provision_app_role() -> None:
    """Create the non-superuser app role and grant it CRUD on the migrated schema."""
    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                sa.text(
                    f"""
                    DO $$ BEGIN
                      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{_APP_USER}') THEN
                        CREATE ROLE {_APP_USER} LOGIN PASSWORD '{_APP_PASS}' NOSUPERUSER NOBYPASSRLS;
                      END IF;
                    END $$;
                    """
                )
            )
            for stmt in (
                f"GRANT USAGE ON SCHEMA public TO {_APP_USER}",
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {_APP_USER}",
                f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {_APP_USER}",
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {_APP_USER}",
            ):
                await conn.execute(sa.text(stmt))
    finally:
        await engine.dispose()


async def _truncate_all() -> None:
    """Wipe every table between tests (admin connection bypasses RLS)."""
    from app.db import Base

    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        if tables:
            async with engine.connect() as conn:
                # Background tasks (fire-and-forget screening) abandoned when a
                # test's event loop closed can leave transactions open; TRUNCATE
                # would wait on their locks forever. Kill stragglers first.
                await conn.execute(
                    sa.text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                    )
                )
                await conn.execute(sa.text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    finally:
        await engine.dispose()


def _run_migrations() -> None:
    """Run `alembic upgrade head` as the admin role (own process → no event-loop clash)."""
    env = {**os.environ, "DATABASE_URL": ADMIN_URL, "ENV": "test"}
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=str(_BACKEND_DIR),
        env=env,
        check=True,
    )


# ── Session-scoped database lifecycle ───────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def _database():
    asyncio.run(_ensure_database())
    _run_migrations()
    asyncio.run(_provision_app_role())

    # Rebuild the app engine/settings so they pick up the test (app-role) URL.
    from app.config import get_settings
    import app.db as db

    get_settings.cache_clear()
    db._engine = None
    db._session_factory = None
    yield


@pytest.fixture(autouse=True)
def _clean_tables(_database):
    asyncio.run(_truncate_all())
    yield


async def _flush_rate_limits() -> None:
    """The submission rate limit (5/IP/hr) lives in the shared dev Redis; every
    test request comes from the same ASGI test client "IP", so leftover counters
    from previous tests/runs would 429 unrelated tests."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    try:
        keys = [key async for key in client.scan_iter("ratelimit:cv:*")]
        if keys:
            await client.delete(*keys)
    except Exception:
        pass  # Redis optional in some environments
    finally:
        await client.aclose()


@pytest.fixture(autouse=True)
def _clean_rate_limits(_database):
    asyncio.run(_flush_rate_limits())
    yield


@pytest.fixture(autouse=True)
def _reset_async_singletons(_database):
    """
    The app's DB engine and Redis client are module singletons whose pooled
    connections are bound to the event loop they were created on. pytest-asyncio
    gives every test a fresh loop, so a singleton leaking across tests produces
    'RuntimeError: Event loop is closed' 500s in later tests.
    """
    yield
    import app.db as db
    from app import redis_client

    db._engine = None
    db._session_factory = None
    redis_client._redis = None


# ── App + seed fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def app(_database):
    from app.main import create_app

    return create_app()


def _mint_token(user_id: str, company_id: str, role: str = "admin") -> str:
    from app.config import get_settings

    settings = get_settings()
    payload = {
        "sub": user_id,
        "company_id": company_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


async def _seed_company_admin() -> tuple[str, str, str]:
    """Insert a company + active admin user. Returns (company_id, user_id, token)."""
    company_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    pw_hash = bcrypt.hashpw(b"TestPass123!", bcrypt.gensalt()).decode()

    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                sa.text("INSERT INTO companies (id, name) VALUES (:id, :name)"),
                {"id": company_id, "name": f"Test Co {company_id[:8]}"},
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO users (id, company_id, email, password_hash, role, is_active) "
                    "VALUES (:id, :cid, :email, :ph, 'admin', true)"
                ),
                {
                    "id": user_id,
                    "cid": company_id,
                    "email": f"admin-{user_id[:8]}@test.local",
                    "ph": pw_hash,
                },
            )
    finally:
        await engine.dispose()
    return company_id, user_id, _mint_token(user_id, company_id)


async def _seed_active_job(company_id: str, created_by: str) -> str:
    """Insert an active job with criteria. Returns job_id."""
    job_id = str(uuid.uuid4())
    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            # streaming_interview=false: these fixtures exercise the turn-based
            # contract; the streaming tests opt in via monkeypatched sessions.
            await conn.execute(
                sa.text(
                    "INSERT INTO jobs (id, company_id, title, status, created_by, streaming_interview) "
                    "VALUES (:id, :cid, :title, 'active', :cb, false)"
                ),
                {"id": job_id, "cid": company_id, "title": "Senior Backend Engineer", "cb": created_by},
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO job_criteria "
                    "(id, job_id, company_id, experience_level, evaluation_dimensions, min_screening_score) "
                    "VALUES (:id, :jid, :cid, 'senior', "
                    "CAST(:dims AS jsonb), 60)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "jid": job_id,
                    "cid": company_id,
                    "dims": '[{"name": "Technical Depth", "weight": 1.0, "description": "Core skills"}]',
                },
            )
    finally:
        await engine.dispose()
    return job_id


async def _seed_application(
    company_id: str, job_id: str, *, with_interview_token: bool = False
) -> tuple[str, str | None]:
    """Insert a candidate + application. Returns (application_id, interview_token)."""
    candidate_id = str(uuid.uuid4())
    application_id = str(uuid.uuid4())
    token = str(uuid.uuid4()) if with_interview_token else None
    expires = datetime.now(timezone.utc) + timedelta(days=7) if with_interview_token else None

    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                sa.text("INSERT INTO candidates (id, email, full_name) VALUES (:id, :email, :name)"),
                {"id": candidate_id, "email": f"cand-{candidate_id[:8]}@test.local", "name": "Jane Doe"},
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO applications "
                    "(id, job_id, candidate_id, company_id, cv_blob_key, screening_status, status, "
                    " interview_token, interview_token_expires_at) "
                    "VALUES (:id, :jid, :cand, :cid, :blob, 'qualified', :status, :tok, :exp)"
                ),
                {
                    "id": application_id,
                    "jid": job_id,
                    "cand": candidate_id,
                    "cid": company_id,
                    "blob": f"cvs/{job_id}/{application_id}.pdf",
                    "status": "invited" if with_interview_token else "qualified",
                    "tok": token,
                    "exp": expires,
                },
            )
    finally:
        await engine.dispose()
    return application_id, token


@pytest.fixture
async def active_job_token() -> tuple[str, str]:
    company_id, user_id, token = await _seed_company_admin()
    job_id = await _seed_active_job(company_id, user_id)
    return token, job_id


@pytest.fixture
async def active_job() -> str:
    company_id, user_id, _ = await _seed_company_admin()
    return await _seed_active_job(company_id, user_id)


@pytest.fixture
async def interview_token() -> str:
    company_id, user_id, _ = await _seed_company_admin()
    job_id = await _seed_active_job(company_id, user_id)
    _, token = await _seed_application(company_id, job_id, with_interview_token=True)
    assert token is not None
    return token


@pytest.fixture
async def completed_interview_session() -> tuple[str, str, str]:
    """Seed a completed interview session with a short transcript."""
    company_id, user_id, _ = await _seed_company_admin()
    job_id = await _seed_active_job(company_id, user_id)
    application_id, _ = await _seed_application(company_id, job_id)
    session_id = str(uuid.uuid4())

    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO interview_sessions "
                    "(id, application_id, company_id, mode, status, turn_count, completed_at) "
                    "VALUES (:id, :aid, :cid, 'voice', 'completed', 2, now())"
                ),
                {"id": session_id, "aid": application_id, "cid": company_id},
            )
            for turn_index, (speaker, text) in enumerate(
                [
                    ("ai", "Tell me about your experience with distributed systems."),
                    ("candidate", "I led the design of a Kafka-based event pipeline."),
                ]
            ):
                await conn.execute(
                    sa.text(
                        "INSERT INTO interview_messages "
                        "(id, session_id, company_id, turn_index, speaker, content_text) "
                        "VALUES (:id, :sid, :cid, :ti, :sp, :txt)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "sid": session_id,
                        "cid": company_id,
                        "ti": turn_index,
                        "sp": speaker,
                        "txt": text,
                    },
                )
    finally:
        await engine.dispose()
    return session_id, company_id, application_id
