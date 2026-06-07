# Quickstart Validation: Analytics Dashboard

Validates V2-2 end-to-end. Assumes the MVP stack is running (see the
[MVP quickstart](../../001-ai-hiring-platform/quickstart.md)) with a recruiter/admin
account and at least one job that has applications across mixed statuses.

## Prerequisites

- Running stack (`docker compose -f infra/docker-compose.yml up -d`).
- A recruiter or admin bearer token: `$TOKEN`.
- A job id `$JOB_ID` with 20+ applications spanning received / qualified / interviewed /
  evaluated, plus at least one completed evaluation (for average score and timings).

## Scenario 1 — Per-job funnel (US1)

```bash
curl -s http://localhost:8000/jobs/$JOB_ID/analytics \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Expected**: `200` with a `JobAnalyticsResponse` (see [contracts/api.md](contracts/api.md)).
Cross-check against the raw records — funnel counts, `qualification_rate`,
`interview_completion_rate`, `avg_evaluation_score`, and p50/p95 timings must match a
direct query (SC-001). Re-running yields identical percentiles (SC-003).

## Scenario 2 — Zero-applications job (edge case)

```bash
curl -s http://localhost:8000/jobs/$EMPTY_JOB_ID/analytics \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Expected**: `200` with all funnel counts `0` and rates/averages `null` (rendered "—") —
no division-by-zero, no error.

## Scenario 3 — Company-wide overview (US2)

```bash
curl -s http://localhost:8000/analytics/overview \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Expected**: `200` with `period` = current month, `total_applications`,
`screening_pass_rate`, `avg_evaluation_score`, and the `jobs` list. Totals reflect only
applications created in the current calendar month.

## Scenario 4 — Tenant isolation (FR-007)

Using **company B's** token, request **company A's** job analytics:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  http://localhost:8000/jobs/$COMPANY_A_JOB_ID/analytics \
  -H "Authorization: Bearer $COMPANY_B_TOKEN"
```

**Expected**: `404` (the job is invisible across tenants); the overview for company B
never includes company A's numbers.

## Scenario 5 — AuthZ

- No / invalid token → `401`.
- A non-recruiter/admin authenticated user → `403`.

## Frontend check

Log in as a recruiter. **Expected**: the post-login landing is the company overview with
KPI cards above the job list (FR-005). Opening a job shows the funnel chart, score
distribution, and timing stats; each chart has an accessible label and a tabular/text
fallback (WCAG 2.1 AA).
