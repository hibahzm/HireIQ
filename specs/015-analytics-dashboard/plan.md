# Implementation Plan: Analytics Dashboard

**Branch**: `015-analytics-dashboard` | **Date**: 2026-06-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/015-analytics-dashboard/spec.md`

---

## Summary

Add two read-only, tenant-scoped analytics endpoints and their UI: a **per-job hiring
funnel** (received → qualified → interviewed → evaluated, with qualification /
interview-completion rates, average evaluation score, and p50/p95 time-to-screen &
time-to-evaluate) and a **company-wide overview** (total applications this calendar
month, overall screening pass rate, overall average evaluation score) that becomes the
post-login landing surface for all recruiters and admins. All metrics are **computed on
read** from existing data — funnel counts from `applications` / `interview_sessions` /
`evaluations`; time-to-screen from the `audit_logs` `cv.screening.started/completed`
events the MVP already writes; and time-to-evaluate from `evaluations.created_at −
interview_sessions.completed_at`. No new write-path data, entities, or migrations are
required (a read-only supporting index may
be added if profiling needs it). Percentiles are computed in SQL with `percentile_cont`
so results are deterministic and meet the p95 ≤ 300 ms gate.

---

## Technical Context

**Language/Version**: Python 3.12 (backend), Node 20 / TypeScript 5 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy async, asyncpg (backend, unchanged);
**adds `recharts`** to the frontend for funnel / distribution / timing charts.

**Storage**: PostgreSQL with RLS. **No schema change.** Reads `applications`,
`interview_sessions`, `evaluations`, and `audit_logs` (all existing). An optional
read-only composite index on `audit_logs (company_id, event_type)` may be added if the
timing aggregation misses the latency gate — additive, no data change.

**Testing**: `pytest` + `pytest-asyncio` (backend); accuracy + tenant-isolation
integration tests for the analytics endpoints (see Constitution Check VI/VIII below).

**Target Platform**: Docker Compose (dev) / Azure Container Apps (prod) — unchanged.

**Project Type**: Multi-service web app (backend + agents + frontend) — unchanged.

**Performance Goals**: Both analytics endpoints respond at **p95 ≤ 300 ms** under the
constitution's load profile (SC-004), computed on read (no pre-aggregation).

**Constraints**: Tenant isolation on every query (RLS); "this period" = current calendar
month, fixed; compute-on-read only (no materialized views); responses expose aggregates
only — no candidate PII.

**Scale/Scope**: V2 scale (~20 companies, hundreds of applications/job). Two GET
endpoints, one repository, one service, two frontend pages, one charting dependency.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. User-First Design | ✅ PASS | US1/US2 in spec; charts ship with accessible labels + a tabular/text fallback so the funnel and percentiles meet WCAG 2.1 AA, not color/shape alone. |
| II. Async-First Python | ✅ PASS | Analytics repository/service/routes are `async`; all DB access via the SQLAlchemy async engine (asyncpg). No blocking calls. |
| III. Clean Architecture | ✅ PASS | New `AnalyticsRepository` holds all aggregation SQL; `AnalyticsService` computes rates (with ÷0 guards) and assembles DTOs; the router is a thin orchestrator wired via `Depends()`. |
| IV. Secrets & Credentials Hygiene | ✅ PASS | No new secrets or external services. |
| V. AI Agent Safety & PII Protection | ✅ PASS | No agent/LLM calls. Responses are numeric aggregates only — no candidate names, emails, rationale, or transcripts. |
| VI. Multi-Tenant Data Isolation | ✅ PASS | Every query runs through the authenticated, RLS-scoped session (`company_id` from RLS context); a dedicated cross-tenant isolation test is mandatory (FR-007). |
| VII. Observability & Reliability | ✅ PASS | Structured logging + correlation ID inherited on the new routes; `/health` unaffected. Analytics are reads, not pipeline actions, so no new `audit_log` writes are required. |
| VIII. Test Coverage | ✅ PASS | Analytics is **not** one of the four TDD-mandated domains, so TDD is not gating here; however, accuracy (SC-001) and tenant-isolation (Principle VI) integration tests are included as required quality gates for this feature. |

**Performance gate**: SC-004 (p95 ≤ 300 ms) is enforced by the existing `infra/perf/`
harness; an analytics scenario is added there. Compute-on-read + SQL `percentile_cont`
+ existing indexes are expected to clear the gate at V2 scale.

**Post-Phase 1 re-check**: ✅ No new violations — the design adds two read endpoints, a
repository, a service, and a charting dependency; it introduces no new write paths,
entities, secrets, or agent calls.

## Project Structure

### Documentation (this feature)

```text
specs/015-analytics-dashboard/
├── plan.md              # This file
├── research.md          # Phase 0 — metric-derivation & charting decisions
├── data-model.md        # Phase 1 — read model (no schema change) + metric definitions
├── quickstart.md        # Phase 1 — validation guide for both endpoints
├── contracts/
│   └── api.md           # Phase 1 — analytics endpoint contracts
└── tasks.md             # Phase 2 — generated by /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── repositories/
│   │   └── analytics_repository.py   # NEW — aggregation SQL (funnel, rates, percentiles)
│   ├── services/
│   │   └── analytics_service.py      # NEW — orchestration, ÷0-safe rate computation, DTO assembly
│   ├── schemas/
│   │   └── analytics.py              # NEW — JobAnalyticsResponse, CompanyOverviewResponse
│   └── api/routers/
│       └── analytics.py              # NEW — GET /jobs/{job_id}/analytics, GET /analytics/overview
└── tests/integration/
    └── test_analytics.py             # NEW — accuracy (SC-001/003), ÷0 edge cases, tenant isolation (FR-007)

frontend/
├── package.json                      # + recharts dependency
├── src/services/api.ts               # + api.analytics.job()/overview() client + types (central convention)
└── src/pages/analytics/
    ├── CompanyOverviewPage.tsx       # NEW — post-login landing: KPI cards above the job list
    └── JobAnalyticsPage.tsx          # NEW — funnel + score distribution + timing stats
```

**Structure Decision**: Follows the MVP's repository → service → thin-router layering.
A single `AnalyticsRepository` owns all aggregation SQL (Principle III); the service
adds rate math and ÷0 guards; the router exposes two authenticated GET endpoints. The
frontend adds an analytics page pair and Recharts; the company overview replaces the
post-login landing while keeping the job list beneath the KPI cards.

## Complexity Tracking

No constitution violations. No justification table needed.
