# Feature Specification: Analytics Dashboard

**Feature Branch**: `015-analytics-dashboard`

**Created**: 2026-06-07

**Status**: Draft

**Input**: V2-2 — recruiters see aggregated hiring-funnel metrics per job and company-wide

## Clarifications

### Session 2026-06-07

- Q: What performance target must the analytics endpoints meet, and how? → A: p95 ≤ 300 ms (the constitution's sync-REST gate), computed on read with proper indexes — no pre-aggregation or materialized views at V2 scale.
- Q: Who can access the company-wide overview dashboard? → A: All authenticated recruiters and admins (company-scoped via RLS); it is the post-login landing surface for everyone.
- Q: How is "this period" defined for company-wide totals? → A: The current calendar month, fixed (not user-selectable in V2).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Recruiter Views a Job's Hiring Funnel (Priority: P1)

A recruiter opens a job and sees an analytics view: how many applications were
received, what share qualified, how many completed an interview, the average
evaluation score, and how long screening and evaluation took (p50/p95). This lets
them judge pipeline health and where candidates drop off — without exporting data or
counting rows by hand.

**Why this priority**: Per-job funnel insight is the core value of the analytics
feature and is independently useful even without the company-wide view.

**Independent Test**: For a job with 20+ applications across mixed statuses, open its
analytics view and confirm the funnel counts, rates, average score, and timing
percentiles match the underlying records.

**Acceptance Scenarios**:

1. **Given** a job with applications in various statuses, **When** the recruiter opens
   the job's analytics, **Then** they see counts per funnel stage (received →
   qualified → interviewed → evaluated) and the qualification and interview-completion
   rates.
2. **Given** completed evaluations exist for the job, **When** the recruiter views
   analytics, **Then** they see the average overall evaluation score.
3. **Given** applications with screening/evaluation timestamps, **When** the recruiter
   views analytics, **Then** they see p50 and p95 time-to-screen and time-to-evaluate.
4. **Given** a job with zero applications, **When** the recruiter opens analytics,
   **Then** the view renders with zeroed metrics and no error (no division-by-zero).

---

### User Story 2 — Company-Wide Overview Dashboard (Priority: P2)

When a recruiter or admin logs in, they land on a company-wide overview showing
aggregate KPIs across all jobs — total applications this period, overall screening
pass rate, and overall average evaluation score — above the list of jobs.

**Why this priority**: A useful at-a-glance summary, but secondary to the per-job
funnel; depends on the same aggregation logic.

**Independent Test**: With multiple active jobs, log in and confirm the overview shows
correct company-wide aggregates and lists the jobs below.

**Acceptance Scenarios**:

1. **Given** a company with several jobs and applications, **When** a user logs in,
   **Then** the overview shows total applications, overall pass rate, and overall
   average evaluation score for the company.
2. **Given** the overview is the landing page, **When** the user navigates, **Then**
   the job list remains accessible below the KPI cards.

---

### Edge Cases

- A job/company with zero applications or zero evaluations shows 0 (or "—") for rates
  and averages rather than erroring.
- Rate denominators (qualification rate, interview-completion rate) guard against
  division by zero.
- Analytics respect tenant isolation: a user only ever sees their own company's
  aggregates (inherits MVP RLS).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST compute per-job funnel metrics: application counts by
  status, qualification rate (qualified ÷ received), interview-completion rate
  (interviewed ÷ qualified), average overall evaluation score, and p50/p95
  time-to-screen and time-to-evaluate.
- **FR-002**: Recruiters and admins MUST be able to retrieve per-job analytics via an
  authenticated, tenant-scoped endpoint.
- **FR-003**: Any authenticated recruiter or admin MUST be able to retrieve
  company-wide aggregate analytics via an authenticated endpoint, all scoped to the
  current calendar month (fixed, not user-selectable in V2): total applications,
  overall screening pass rate, and overall average evaluation score — each computed over
  the applications created in that month.
- **FR-004**: The per-job analytics page MUST visualize the funnel (stage counts), the
  evaluation-score distribution, and the time-to-screen / time-to-evaluate stats.
- **FR-005**: The company-wide overview MUST present KPI cards above the job list and
  serve as the post-login landing surface for all authenticated recruiters and admins.
- **FR-006**: All analytics MUST be derived from existing timestamps and statuses on
  `applications` and `evaluations` — no new write-path data collection is required.
- **FR-007**: All analytics queries MUST be tenant-isolated; no cross-company data may
  appear in any metric.

### Key Entities

No new entities. Metrics are derived from existing `applications` (status,
created_at, screening timestamps) and `evaluations` (overall_score, created_at).

## Success Criteria *(mandatory)*

- **SC-001**: For a job with 20+ applications, every funnel count and rate matches a
  direct query of the underlying records (100% accuracy).
- **SC-002**: `GET /analytics/overview` returns the three company-wide KPIs (total
  applications, screening pass rate, average evaluation score) plus the job list, and
  the overview page renders the KPI cards above the job list — no manual data export
  required.
- **SC-003**: Timing percentiles (p50/p95) are computed from real timestamps and are
  reproducible across reloads (deterministic for a fixed dataset).
- **SC-004**: Both analytics endpoints (per-job and company-wide) respond within
  p95 ≤ 300 ms under the constitution's defined load profile, computed on read (no
  pre-aggregation or materialized views).

## Assumptions

- "This period" for company-wide totals is the current calendar month, fixed (not
  user-selectable in V2).
- Metrics are computed on read (live queries) with appropriate indexes; no
  pre-aggregation/materialized views are used at MVP-V2 scale (hundreds of applications
  per job), and reads must still meet the p95 ≤ 300 ms gate (SC-004).

## Dependencies

- Builds on MVP `applications` and `evaluations` data and the existing auth/RLS layer.
- Adds a charting library (e.g., Recharts) to the frontend.
