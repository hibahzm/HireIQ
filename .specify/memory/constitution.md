<!-- SYNC IMPACT REPORT
Version change: 1.1.0 → 1.1.1
Modified principles:
  - II. Test-First Development → VIII. Test Coverage (domain-specific required areas added)
  - III. API-First Architecture → III. Clean Architecture (repository pattern + DI rules added)
  - IV. Security & Privacy by Design → IV. Secrets & Credentials Hygiene (focused on secrets mgmt)
  - V. Simplicity & Maintainability → absorbed into other principles; removed as standalone
Added principles:
  - II. Async-First Python (new)
  - V. AI Agent Safety & PII Protection (new)
  - VI. Multi-Tenant Data Isolation (new)
  - VII. Observability & Reliability (materially expanded from observability note in v1.0.0)
Removed sections: None
Deferred TODOs resolved:
  - TODO(TECH_STACK): Python/FastAPI confirmed (resolved)
Remaining deferred TODOs:
  - (none) — TODO(PERFORMANCE_BASELINE) resolved in v1.1.1: load profile defined
    under Technical Standards → Performance and enforced by infra/perf/.
Templates requiring updates:
  - .specify/templates/plan-template.md  ✅ No structural changes required
  - .specify/templates/spec-template.md  ✅ No structural changes required
  - .specify/templates/tasks-template.md ✅ No structural changes required
-->

# HireIQ Constitution

## Core Principles

### I. User-First Design
Every feature MUST serve a concrete, demonstrable need for either recruiters or candidates.
A feature without a user story in `spec.md` is not schedulable.
All interfaces MUST be intuitive, accessible (WCAG 2.1 AA minimum), and responsive across
desktop and mobile viewports.

### II. Async-First Python
All service, repository, and route functions MUST be declared `async`.
Synchronous database calls are prohibited — use only async-compatible drivers
(e.g., `asyncpg`, SQLAlchemy async engine).
Synchronous HTTP calls are prohibited — use `httpx.AsyncClient` or equivalent.
Blocking the event loop is treated as a defect and blocks merge.

### III. Clean Architecture
All database access MUST go through a repository layer — no raw queries in routes or services.
Route handlers are thin orchestrators only; business logic MUST NOT leak into them.
Dependencies MUST be wired via FastAPI `Depends()` — nothing is instantiated manually in routes.
This separation ensures testability: repositories and services can be mocked at the `Depends()`
boundary without patching internals.

### IV. Secrets & Credentials Hygiene
No secret, credential, API key, or connection string may be hardcoded anywhere in the codebase.
All secrets MUST be sourced from `config.py` backed by Vault or Azure Key Vault.
`.env` files, secret files, and model weight files MUST NOT be committed to git under any
circumstances. A PR containing such a commit is rejected immediately regardless of review status.
`.gitignore` MUST cover `.env*`, `*.pem`, `*.key`, and model directories at project init.

### V. AI Agent Safety & PII Protection
Every agent invocation MUST route its input and output through the guardrail registry.
No agent may write output to storage before a PII redaction pass has been applied.
Bypassing the guardrail registry (e.g., calling the LLM client directly from a service) is a
policy violation and blocks merge.
Rationale: HireIQ processes sensitive candidate data; unredacted PII in storage creates
legal and compliance risk.

### VI. Multi-Tenant Data Isolation
Row-Level Security (RLS) MUST be set on every database connection before the first query.
RLS enforcement is the responsibility of the connection middleware — it MUST NOT be delegated
to business logic or individual service calls.
Every tenant-scoped table MUST have a `company_id` column and a corresponding RLS policy.
No exceptions are permitted regardless of table size or perceived sensitivity.
Cross-tenant data leakage under any code path is a critical defect.

### VII. Observability & Reliability
Every significant pipeline action (CV screening start/end, interview turn, evaluation result)
MUST be written to `audit_log` with timestamp, actor, tenant, and outcome.
Both `api` and `agents` services MUST expose a `/health` endpoint that returns a machine-readable
status; health endpoints are required before any deployment.
Structured logging with a correlation ID MUST be present on all API request paths.

### VIII. Test Coverage (NON-NEGOTIABLE)
Automated tests are required for the following domains — no merge is permitted without them:
- Authentication and authorization flows
- CV screening pipeline (input → guardrails → output → storage)
- Voice interview turn handling (input, turn sequencing, output)
- Evaluation pipeline (scoring, aggregation, result storage)

TDD cycle is mandatory for these domains: write tests → reviewer approval → tests fail →
implement → tests pass → merge.
Tests for other areas are encouraged but not gating.

## Technical Standards

- **Language/Runtime**: Python (async) with FastAPI.
- **Database**: PostgreSQL with Row-Level Security; async access via `asyncpg` or
  SQLAlchemy async engine.
- **Secrets Management**: `config.py` backed by Vault or Azure Key Vault; no `.env` in CI/CD.
- **Testing**: `pytest` with `pytest-asyncio`; repositories and services tested via dependency
  injection mocks.
- **Performance**: API responses MUST meet p95 ≤ 300 ms under the defined load
  profile: 50 concurrent users, ~200 req/s on synchronous REST endpoints,
  sustained 5 minutes, at MVP launch scale (~20 companies, ~500 applications/job).
  Async pipelines are budgeted separately by their SLAs (CV screening ≤ 2 min /
  SC-002; evaluation ≤ 5 min / SC-004). The profile is enforced by the load
  harness in `infra/perf/` (Locust + `check_p95.py` gate).
- **Accessibility**: All UI components MUST conform to WCAG 2.1 AA.
- **Code Quality**: `ruff` for linting and formatting; enforced in CI; lint errors block merge.
- **Dependency Vetting**: All new dependencies evaluated for CVEs, maintenance status, and
  license compatibility before adoption.

## Development Workflow

- **Branching**: Feature branches created from `main` following `NNN-feature-name` convention.
  Direct pushes to `main` are prohibited.
- **Commit Messages**: Commits MUST have meaningful messages describing the why, not just the what.
  Vague messages ("fix", "update", "wip") are not acceptable on feature branches.
- **Reviews**: All pull requests require at least one peer review and passing CI before merge.
- **CI/CD**: Automated tests, linting, and security scans MUST pass before any merge to `main`.
- **Releases**: Semantic versioning (MAJOR.MINOR.PATCH); a changelog entry is required per release.
- **Documentation**: Each feature MUST update relevant docs (API contracts, quickstart, README)
  before the branch is closed.
- **Excluded from VCS**: `.env*`, secrets, model weights, and compiled artifacts MUST be listed
  in `.gitignore` and are never committed.

## Governance

This constitution supersedes all informal project conventions.
Amendments require:
1. A documented rationale explaining why the change is needed.
2. Review and approval by the project lead.
3. A migration plan for any work-in-progress features affected by the amendment.
4. A version increment following the policy below.

**Versioning policy**:
- MAJOR: Backward-incompatible principle removal or redefinition.
- MINOR: New principle or section added, or materially expanded guidance.
- PATCH: Clarifications, wording fixes, non-semantic refinements.

All PRs and reviews MUST verify compliance with this constitution.
For runtime development guidance, refer to `CLAUDE.md`.

**Version**: 1.1.1 | **Ratified**: 2026-06-04 | **Last Amended**: 2026-06-07
