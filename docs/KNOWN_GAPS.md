# Known Gaps & Tracked Follow-ups

This file tracks accepted gaps at the time the MVP (`001-ai-hiring-platform`,
Phases 1–8) was merged to `main`. Convert each into a GitHub issue when the
`gh` CLI / web access is available.

## 1. Integration-test harness is not wired up (CI not green)

**Status:** implemented — pending validation against a real pgvector Postgres.

`backend/tests/integration/conftest.py` now exists and provides the previously
missing fixtures:
- `app` (`create_app()` with `ENV=test`);
- a session-scoped DB lifecycle that runs `alembic upgrade head` as the
  admin/superuser role and truncates all tables between tests;
- a **non-superuser app role** (`hireiq_test_app`, `NOSUPERUSER NOBYPASSRLS`) that
  the app connects as, so the `FORCE ROW LEVEL SECURITY` policies are actually
  enforced for `test_tenant_isolation.py` (SC-005);
- seed fixtures (`active_job`, `active_job_token`, `completed_interview_session`,
  `interview_token`) built via direct DB inserts (no OpenAI/agents calls).

**Remaining to fully close:** run it once against a real pgvector Postgres
(CI image or `infra/docker-compose.yml`) and fix any field/role-grant details that
can't be validated without a live DB. Connection is configurable via
`TEST_DATABASE_URL` (admin) / `TEST_APP_DATABASE_URL` (non-superuser app role);
defaults match the dev-compose Postgres with a dedicated `hireiq_test` database.

## 2. ~~`migration_user` role fix is unverified locally~~ (obsolete)

**Status:** resolved — no longer applicable.

`alembic/env.py` no longer creates or `SET ROLE`s to a `migration_user`/BYPASSRLS
role. Migrations now run as the connecting role (a superuser in dev/CI, the DB
owner on Azure Postgres), which is required for `CREATE EXTENSION vector` and is
unaffected by `FORCE ROW LEVEL SECURITY` (DDL only). Still worth a one-time
`docker compose -f infra/docker-compose.yml up` (the `migrate` one-shot) to
confirm a clean `upgrade head`.

## 3. Phase 8 audit harnesses require live infra to execute

**Status:** tooling delivered, execution pending.

`T083` (e2e-validate.sh), `T084` (Locust perf + p95 gate), and `T084b` (RAGAS
quality gate) are wired but need Docker + a real `OPENAI_API_KEY` to run. The
`ragas-quality` CI job is gated on `secrets.OPENAI_API_KEY` and only runs on
pushes to `main`.
