# Tasks: Analytics Dashboard

**Input**: Design documents from `specs/015-analytics-dashboard/`

**Prerequisites**: [plan.md](plan.md) · [spec.md](spec.md) · [research.md](research.md) · [data-model.md](data-model.md) · [contracts/api.md](contracts/api.md) · [quickstart.md](quickstart.md)

**Tests**: Analytics is **not** one of the four Constitution-VIII TDD-mandated domains, so
TDD is not gating here. However, **accuracy (SC-001/003) and tenant-isolation (Principle
VI / FR-007) integration tests are required quality gates** for this feature and are
written before the corresponding endpoints.

> Scoped task list for V2-2 (analytics dashboard). Two user stories: US1 (per-job funnel,
> P1) and US2 (company-wide overview, P2). Builds entirely on the existing MVP data — no
> schema change, no new write paths.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared in-progress dependencies)
- **[Story]**: `US1` / `US2` map to the user stories in [spec.md](spec.md)
- Exact file paths are included in every description

---

## Phase 1: Setup

- [X] T001 [P] Add `recharts` to `frontend/package.json` dependencies and install (charting for funnel / score distribution / timing visuals); rebuild the frontend image / reinstall deps

---

## Phase 2: Foundational (Blocking Prerequisites)

**Shared scaffolding both user stories depend on.** Complete before Phase 3.

- [X] T002 [P] Create analytics response schemas in `backend/app/schemas/analytics.py` — `FunnelCounts`, `TimingPercentiles` (`p50`, `p95`), `ScoreBucket`, `JobAnalyticsResponse`, and `CompanyOverviewResponse` per [contracts/api.md](contracts/api.md); rates/averages/timings typed as nullable
- [X] T003 Create `AnalyticsRepository` skeleton in `backend/app/repositories/analytics_repository.py` — class taking an `AsyncSession`; all aggregation SQL lives here (Principle III); no raw queries leak to service/router
- [X] T004 Create `AnalyticsService` skeleton in `backend/app/services/analytics_service.py` — class wired to `AnalyticsRepository`; will hold ÷0-safe rate math and DTO assembly
- [X] T005 Create analytics router in `backend/app/api/routers/analytics.py` (auth via `require_recruiter_or_admin`, session via `get_authed_session`, both `Depends()`-wired) and register it on the app (`include_router`) so routes resolve once endpoints are added
- [X] T006 [P] Extend the central frontend API client in `frontend/src/services/api.ts` — typed `api.analytics.job(jobId)` and `api.analytics.overview()` plus `JobAnalytics`/`CompanyOverview` types matching [contracts/api.md](contracts/api.md) (follows the codebase convention of one shared client, rather than a per-page `analyticsApi.ts`)

---

## Phase 3: User Story 1 — Recruiter Views a Job's Hiring Funnel (Priority: P1) 🎯

**Goal**: A per-job analytics view showing funnel counts, qualification / interview-completion
rates, average evaluation score, score distribution, and p50/p95 time-to-screen &
time-to-evaluate — accurate, tenant-isolated, ÷0-safe, p95 ≤ 300 ms.

**Independent Test**: For a job with 20+ mixed-status applications, `GET /jobs/{job_id}/analytics`
returns funnel/rates/score/timings matching a direct query (SC-001); a zero-application
job returns zeroed counts and `null` rates with no error; a cross-tenant request 404s.
See [quickstart.md](quickstart.md) Scenarios 1, 2, 4.

### Tests for User Story 1 (required quality gates — write FIRST, confirm FAILING before T010)

- [X] T007 [P] [US1] Write failing integration test: per-job analytics accuracy + zero-app edge in `backend/tests/integration/test_analytics.py` — seed a job with mixed-status applications, completed interviews, and evaluations; assert funnel counts, qualification/interview-completion rates, avg score, score distribution, and p50/p95 timings match direct queries; assert a zero-application job returns all-zero counts and `null` rates (no ÷0 error)
- [X] T008 [P] [US1] Write failing integration test: per-job tenant isolation in `backend/tests/integration/test_analytics.py` — company B's token requesting company A's job returns 404 and never leaks A's numbers (FR-007)

### Implementation for User Story 1

- [X] T009 [US1] Add per-job aggregation methods to `AnalyticsRepository` in `backend/app/repositories/analytics_repository.py` — funnel counts (received / qualified / interviewed via `interview_sessions.completed_at` / evaluated via `evaluations`), `AVG(overall_score)`, score-distribution buckets, and p50/p95 durations via `percentile_cont(...) WITHIN GROUP`: **time-to-screen** from `audit_logs` `cv.screening.completed − cv.screening.started` pairs, **time-to-evaluate** from `evaluations.created_at − interview_sessions.completed_at` (see [data-model.md](data-model.md) / [research.md](research.md) Decision 3 — note: `audit_logs` is NOT a reliable source for evaluation timing)
- [X] T010 [US1] Add `get_job_analytics(job_id)` to `AnalyticsService` in `backend/app/services/analytics_service.py` — compute ÷0-safe rates (return `null` when denominator is 0) and assemble `JobAnalyticsResponse`
- [X] T011 [US1] Add `GET /jobs/{job_id}/analytics` endpoint in `backend/app/api/routers/analytics.py` — return `JobAnalyticsResponse`; 404 when the job is not in the caller's company (RLS-scoped); 401/403 via the wired auth dep
- [X] T012 [P] [US1] Build `JobAnalyticsPage` in `frontend/src/pages/analytics/JobAnalyticsPage.tsx` — Recharts funnel (bar), score-distribution histogram, and timing (p50/p95) stats; each chart paired with an accessible data table / text summary (WCAG 2.1 AA); fetch via `getJobAnalytics`
- [X] T013 [P] [US1] Wire the per-job analytics route to `JobAnalyticsPage` in the frontend router and add an entry point from the job view

**Checkpoint**: US1 is independently demoable — `GET /jobs/{job_id}/analytics` is accurate,
tenant-isolated, ÷0-safe, and the page renders the funnel/score/timing visuals. Tests
T007/T008 pass.

---

## Phase 4: User Story 2 — Company-Wide Overview Dashboard (Priority: P2)

**Goal**: A post-login landing surface with company-wide KPI cards (total applications this
calendar month, screening pass rate, average evaluation score) above the job list, for all
authenticated recruiters and admins.

**Independent Test**: `GET /analytics/overview` returns current-month totals, pass rate, avg
score, and the job list; a no-token request 401s and a non-recruiter/admin 403s; the UI
lands on the overview with the job list beneath the KPI cards. See [quickstart.md](quickstart.md)
Scenarios 3, 5.

### Tests for User Story 2 (required quality gates — write FIRST, confirm FAILING before T015)

- [X] T014 [P] [US2] Write failing integration test: company overview accuracy + edge + authz in `backend/tests/integration/test_analytics.py` — assert current-calendar-month `total_applications`, `screening_pass_rate`, `avg_evaluation_score`, and the `jobs` list match direct queries; zero-application period yields `null` rate/avg (no error); no token → 401 (the recruiter/admin guard is inherited from `require_recruiter_or_admin`, exercised in auth tests — no authenticated non-recruiter/admin role exists to seed a 403 here); results are company-scoped (no cross-tenant rows)

### Implementation for User Story 2

- [X] T015 [US2] Add company-wide aggregation method to `AnalyticsRepository` in `backend/app/repositories/analytics_repository.py` — current-calendar-month application count (`created_at ≥ date_trunc('month', now())`), pass-rate inputs, `AVG(overall_score)` for the period, and the company's jobs (id, title, status)
- [X] T016 [US2] Add `get_company_overview()` to `AnalyticsService` in `backend/app/services/analytics_service.py` — ÷0-safe pass rate / avg score; assemble `CompanyOverviewResponse` with `period` = current month
- [X] T017 [US2] Add `GET /analytics/overview` endpoint in `backend/app/api/routers/analytics.py` — return `CompanyOverviewResponse`; 401/403 via the wired auth dep
- [X] T018 [P] [US2] Build `CompanyOverviewPage` in `frontend/src/pages/analytics/CompanyOverviewPage.tsx` — KPI cards above the existing job list; fetch via `getCompanyOverview`
- [X] T019 [US2] Make `CompanyOverviewPage` the post-login landing surface in the frontend router (recruiters and admins land here; job list remains accessible beneath the cards — FR-005)

**Checkpoint**: US2 adds the company-wide landing without disturbing US1. Test T014 passes.

---

## Phase 5: Polish & Cross-Cutting

- [ ] T020 [P] Add an analytics scenario to `infra/perf/` (Locust) hitting both endpoints and confirm p95 ≤ 300 ms via the `check_p95.py` gate (SC-004)
- [ ] T021 [P] Validate end-to-end per [quickstart.md](quickstart.md) — Scenarios 1–5 (per-job accuracy, zero-app edge, company overview, tenant isolation, authz) plus the frontend landing check
- [ ] T022 Add a read-only supporting index on `audit_logs (company_id, event_type)` via a new Alembic migration in `backend/alembic/versions/` — **only if** T020 shows the timing aggregation misses the p95 gate (additive, no data change; per [research.md](research.md) Decision 4)

---

## Dependencies & Execution Order

- **Phase 1 (Setup)**: T001 first (frontend charting dep).
- **Phase 2 (Foundational)**: T002–T006 before any user-story work. T002 (schemas) before services/endpoints; T003/T004/T005 create the shared repo/service/router; T006 (API client) is independent [P].
- **Phase 3 (US1)**: Tests T007/T008 before implementation T009–T011.
  - T009 (repo methods) → T010 (service) → T011 (endpoint) are sequential (data flow + shared files).
  - T012/T013 (frontend) run in parallel with the backend chain.
- **Phase 4 (US2)**: Depends on Phase 2. Backend T015→T016→T017 touch the same repo/service/router files as US1, so run them **after** US1's backend chain (file-level coordination), or sequence them explicitly. T014 (test) before T015. T018/T019 (frontend) parallel with backend.
- **Phase 5 (Polish)**: After both stories; T022 is conditional on T020's result.

### Parallel Opportunities

- T002 and T006 (schemas vs frontend client) in parallel.
- Within each story, the frontend tasks (T012/T013, T018/T019) run in parallel with the backend chain.
- T007 and T008 (tests, same new file — write together, independent cases).

---

## Implementation Strategy

Deliver **US1 first as the MVP** (per-job funnel is independently valuable per spec), then
layer US2:

1. Phase 1: add `recharts`.
2. Phase 2: schemas + repo/service/router scaffolding + API client.
3. US1: write failing accuracy + isolation tests → repo methods → service → endpoint →
   page; demo the per-job funnel.
4. US2: write failing overview test → company-wide method → service → endpoint → landing page.
5. Polish: perf-gate the endpoints (SC-004), run the quickstart, add the optional index only
   if profiling requires it.

---

## Notes

- No DB migration is required for the feature itself; the only possible migration (T022) is a
  conditional read-only index.
- All aggregation SQL stays in `AnalyticsRepository` (Principle III); the router is a thin
  orchestrator; everything runs on the RLS-scoped session (Principle VI).
- Responses expose aggregates only — no candidate PII (Principle V).
- Out of scope: user-selectable period, pre-aggregation/materialized views, new write-path
  timestamps.
