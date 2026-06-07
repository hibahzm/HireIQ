# Data Model: Analytics Dashboard (Phase 1)

**No schema changes.** This feature is a read model over existing MVP tables. No new
entities, columns, or migrations. (An optional read-only index may be added per
[research.md](research.md) Decision 4.)

## Source tables (existing)

| Table | Fields used | Role |
|-------|-------------|------|
| `applications` | `id`, `job_id`, `company_id`, `screening_status` (`pending\|qualified\|rejected`), `created_at` | funnel base (received, qualified), period filter |
| `interview_sessions` | `application_id` (unique), `completed_at` | interviewed stage; evaluate-timing start |
| `evaluations` | `application_id` (unique), `overall_score` (0–100), `created_at` | evaluated stage, average score; evaluate-timing end |
| `audit_logs` | `event_type`, `entity_id`, `company_id`, `created_at` | **screening** stage timing only (`cv.screening.started/completed` pairs) |

All tables are tenant-scoped by `company_id` with RLS; analytics queries inherit that
isolation (FR-007).

## Derived read model (computed on request)

### JobAnalytics (per job)

| Field | Type | Definition |
|-------|------|------------|
| `job_id` | uuid | path parameter |
| `funnel.received` | int | `COUNT(applications)` for the job |
| `funnel.qualified` | int | `COUNT(screening_status = 'qualified')` |
| `funnel.interviewed` | int | applications with `interview_sessions.completed_at IS NOT NULL` |
| `funnel.evaluated` | int | applications with an `evaluations` row |
| `qualification_rate` | float \| null | `qualified / received`; `null` if `received = 0` |
| `interview_completion_rate` | float \| null | `interviewed / qualified`; `null` if `qualified = 0` |
| `avg_evaluation_score` | float \| null | `AVG(evaluations.overall_score)`; `null` if none |
| `time_to_screen_seconds` | {p50, p95} \| null | `percentile_cont` over `audit_logs` `cv.screening.completed − cv.screening.started` per application |
| `time_to_evaluate_seconds` | {p50, p95} \| null | `percentile_cont` over `evaluations.created_at − interview_sessions.completed_at` per application |
| `score_distribution` | bucket[] | counts of `overall_score` per band (e.g. 0–20…81–100) |

### CompanyOverview (current calendar month)

| Field | Type | Definition |
|-------|------|------------|
| `period` | string | e.g. `2026-06` (current calendar month) |
| `total_applications` | int | `COUNT(applications WHERE created_at ≥ date_trunc('month', now()))` |
| `screening_pass_rate` | float \| null | qualified / total for the period; `null` if total = 0 |
| `avg_evaluation_score` | float \| null | `AVG(overall_score)` for the period; `null` if none |
| `jobs` | jobSummary[] | the company's jobs (id, title, status) listed beneath the KPI cards |

## Validation / invariants

- **÷0 safety**: every rate/average returns `null` (UI "—") when its denominator/sample is 0.
- **Determinism (SC-003)**: percentiles via SQL `percentile_cont` are reproducible for a
  fixed dataset.
- **Tenant isolation (FR-007)**: no query is parameterized by a client-supplied
  `company_id`; scope comes from the RLS session context only.
- **No PII**: the read model exposes only counts, rates, scores, and durations.

## Out of scope

- No new columns, tables, materialized views, or write-path instrumentation.
- No user-selectable period (fixed to current calendar month in V2).
