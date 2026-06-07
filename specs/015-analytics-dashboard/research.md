# Research: Analytics Dashboard (Phase 0)

All Technical Context unknowns were resolved during `/speckit-clarify` and the grounding
below. No open `NEEDS CLARIFICATION` items remain.

## Decision 1 — Funnel stage derivation (from existing tables)

**Decision**: Compute funnel counts directly from existing columns:

| Stage | Source |
|-------|--------|
| received | `COUNT(applications)` |
| qualified | `COUNT(applications WHERE screening_status = 'qualified')` |
| interviewed | `COUNT(applications` with an `interview_sessions` row where `completed_at IS NOT NULL)` |
| evaluated | `COUNT(applications` with an `evaluations` row) |

**Rationale**: `applications.screening_status` is constrained to
`('pending','qualified','rejected')`; `interview_sessions` has a unique `application_id`
and a real `completed_at`; `evaluations` has a unique `application_id`. All counts are a
single grouped query — no new data. Satisfies FR-001/FR-006.

**Alternatives considered**: Using `applications.status` (8-value enum incl. `interviewing`,
`evaluated`) — rejected as the primary source because status can be manually advanced or
archived, whereas the presence of a completed interview / evaluation row is the ground
truth for "interviewed"/"evaluated".

## Decision 2 — Rates (÷0-safe)

**Decision**: `qualification_rate = qualified / received`;
`interview_completion_rate = interviewed / qualified`. When the denominator is 0, return
`null` (rendered as "—"), never an error.

**Rationale**: Matches the spec edge cases (no division-by-zero). Interview-completion is
expressed relative to the qualified pool (those eligible to be invited), which is the
meaningful funnel conversion.

## Decision 3 — Stage timings (p50/p95) from `audit_logs`

**Decision**: Derive per-application stage durations from the pipeline events the MVP
already writes to `audit_logs` (immutable, has `created_at TIMESTAMPTZ`, indexed on
`event_type` and `(entity_type, entity_id)`):

- `time_to_screen = (cv.screening.completed.created_at) − (cv.screening.started.created_at)`
- `time_to_evaluate = (evaluation.completed.created_at) − (evaluation.started.created_at)`

Aggregate with PostgreSQL `percentile_cont(0.5)` / `percentile_cont(0.95) WITHIN GROUP
(ORDER BY duration_seconds)`.

**Rationale**: These events already exist (Constitution VII), so timings need no new
write-path data (FR-006). `percentile_cont` is computed in-SQL → deterministic for a
fixed dataset (SC-003) and fast. Maps naturally to the screening ≤2 min / evaluation
≤5 min SLAs.

**Implementation note to confirm**: screening events carry `entity_id = application_id`.
The evaluation events' `entity_id` linkage (evaluation vs application) is confirmed at
implementation time; if it is the evaluation id, join `evaluations.id → application_id`.
Fallback if evaluation start/end events are unavailable for a row: `time_to_evaluate =
evaluations.created_at − interview_sessions.completed_at` (both guaranteed columns).

**Alternatives considered**: Adding `screened_at` / `evaluated_at` columns and populating
them on the write path — rejected; violates FR-006 ("no new write-path data collection")
and duplicates data already in `audit_logs`.

## Decision 4 — Compute-on-read, p95 ≤ 300 ms

**Decision**: Serve both endpoints with live aggregation queries (no materialized views,
no rollup tables), relying on existing indexes plus an **optional** additive index on
`audit_logs (company_id, event_type)` if profiling shows the timing query misses the gate.

**Rationale**: Clarified target (SC-004). At V2 scale (hundreds of applications/job) the
grouped counts and `percentile_cont` comfortably fit 300 ms with proper indexing. Avoids
the refresh/invalidation complexity (and FR-006 conflict) of pre-aggregation.

**Alternatives considered**: Short-TTL cache and materialized views — both deferred; the
spec assumption and clarification favor compute-on-read at current scale. Revisit only if
the perf harness shows a miss.

## Decision 5 — Period window = current calendar month

**Decision**: Company-wide KPIs (total applications, screening pass rate, average
evaluation score) are scoped to the **current calendar month** (`date_trunc('month', now())`
≤ `created_at`), fixed and not user-selectable in V2. Per-job analytics are all-time for
that job.

**Rationale**: Clarified in spec Session 2026-06-07. Single, simple window; no extra UI
or query params; deterministic.

## Decision 6 — Charting library: Recharts

**Decision**: Use **Recharts** for the funnel (bar), evaluation-score distribution
(histogram/bar), and timing summary visuals.

**Rationale**: React-native, declarative, lightweight, and already named in the spec's
dependencies. Composable SVG charts that accept ARIA labels, supporting the WCAG fallback
(every chart is paired with an accessible data table / text summary).

**Alternatives considered**: Chart.js (canvas — weaker a11y/text fallback), visx
(lower-level, more code), nivo (heavier). Recharts is the best fit for a small,
accessible dashboard.

## Decision 7 — Authorization & PII posture

**Decision**: Both endpoints require an authenticated recruiter or admin and run through
the RLS-scoped session; responses contain only aggregate numbers (counts, rates, scores,
durations) — never candidate names, emails, rationales, or transcripts.

**Rationale**: Clarified audience (all recruiters + admins, company-scoped). Aggregates-only
keeps the feature outside the PII-redaction path (Principle V) and tenant-safe (Principle VI).
