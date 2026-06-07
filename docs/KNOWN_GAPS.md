# Known Gaps & Tracked Follow-ups

This file tracks accepted gaps at the time the MVP (`001-ai-hiring-platform`,
Phases 1–8) was merged to `main`. Convert each into a GitHub issue when the
`gh` CLI / web access is available.

## 1. Integration-test harness is not wired up (CI not green)

**Status:** open — accepted at merge time.

The integration tests under `backend/tests/integration/` reference an `app`
pytest fixture (and per-file `client(app)` fixtures) plus seed fixtures
(`active_job`, `active_job_token`, `completed_interview_session`,
`interview_token`) that are **not defined** — there is no
`backend/tests/integration/conftest.py`. As a result `pytest tests/ -v` fails at
collection and the CI `backend-lint-test` job is red.

**What's needed to close:**
- `backend/tests/integration/conftest.py` providing:
  - an `app` fixture (`create_app()` with `ENV=test`);
  - a session-scoped test DB lifecycle that runs `alembic upgrade head` against a
    `pgvector/pgvector` Postgres and truncates tables between tests;
  - a **non-superuser app DB role** with `FORCE ROW LEVEL SECURITY` so
    `test_tenant_isolation.py` (SC-005) actually exercises RLS — repositories
    such as `JobRepository.get_by_id` rely on RLS, not app-level company filters,
    so a superuser connection silently bypasses isolation;
  - the seed fixtures listed above (seed via direct DB inserts to avoid external
    OpenAI/agents calls).
- Must be developed/verified against a real Postgres (CI image or local Docker);
  it cannot be validated in an environment without pgvector.

## 2. `migration_user` role fix is unverified locally

**Status:** needs verification.

`alembic/env.py` now idempotently creates the BYPASSRLS `migration_user` role
before `SET ROLE` (commit fixing the prior "role does not exist" failure). This
was syntax-checked only — verify with a `docker compose -f infra/docker-compose.yml up`
(the `migrate` one-shot) or a CI run with Postgres.

## 3. Phase 8 audit harnesses require live infra to execute

**Status:** tooling delivered, execution pending.

`T083` (e2e-validate.sh), `T084` (Locust perf + p95 gate), and `T084b` (RAGAS
quality gate) are wired but need Docker + a real `OPENAI_API_KEY` to run. The
`ragas-quality` CI job is gated on `secrets.OPENAI_API_KEY` and only runs on
pushes to `main`.
