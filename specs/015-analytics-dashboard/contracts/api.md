# API Contract: Analytics Dashboard (Phase 1)

Two new **authenticated, tenant-scoped, read-only** endpoints. Both require a recruiter
or admin (`require_recruiter_or_admin`) over an RLS-scoped session (`get_authed_session`);
scope (`company_id`) comes from the session context, never from the client.

---

## `GET /jobs/{job_id}/analytics` (auth: recruiter/admin)

Per-job hiring-funnel analytics.

### Path parameters

| Name | Type | Notes |
|------|------|-------|
| `job_id` | uuid | Must belong to the caller's company (RLS-enforced). |

### Responses

| Status | When | Body |
|--------|------|------|
| `200 OK` | Job found in tenant | `JobAnalyticsResponse` (below) |
| `401 Unauthorized` | Missing/invalid token | — |
| `403 Forbidden` | Authenticated but not recruiter/admin | — |
| `404 Not Found` | Job not in caller's company | `{ "detail": "Job not found" }` |

### `JobAnalyticsResponse`

```json
{
  "job_id": "uuid",
  "funnel": { "received": 42, "qualified": 18, "interviewed": 11, "evaluated": 9 },
  "qualification_rate": 0.43,
  "interview_completion_rate": 0.61,
  "avg_evaluation_score": 73.5,
  "time_to_screen_seconds": { "p50": 38.0, "p95": 95.0 },
  "time_to_evaluate_seconds": { "p50": 142.0, "p95": 268.0 },
  "score_distribution": [
    { "band": "0-20", "count": 0 },
    { "band": "21-40", "count": 1 },
    { "band": "41-60", "count": 2 },
    { "band": "61-80", "count": 4 },
    { "band": "81-100", "count": 2 }
  ]
}
```

- Any rate/average is `null` when its denominator/sample is 0 (zero-applications job
  returns all-zero funnel and `null` rates — never an error).
- `time_to_*_seconds` is `null` when no completed stage events exist yet.

---

## `GET /analytics/overview` (auth: recruiter/admin)

Company-wide KPIs for the **current calendar month**, plus the job list for the landing
page. Available to all authenticated recruiters and admins.

### Responses

| Status | When | Body |
|--------|------|------|
| `200 OK` | Authenticated recruiter/admin | `CompanyOverviewResponse` (below) |
| `401 Unauthorized` | Missing/invalid token | — |
| `403 Forbidden` | Authenticated but not recruiter/admin | — |

### `CompanyOverviewResponse`

```json
{
  "period": "2026-06",
  "total_applications": 128,
  "screening_pass_rate": 0.47,
  "avg_evaluation_score": 71.2,
  "jobs": [
    { "id": "uuid", "title": "Senior Backend Engineer", "status": "active" }
  ]
}
```

- `period` is the current calendar month (fixed; not user-selectable in V2).
- `screening_pass_rate` / `avg_evaluation_score` are `null` when the period has zero
  applications / evaluations.

---

## Cross-cutting

- **Tenant isolation (FR-007)**: every aggregate is scoped to the caller's company via
  the RLS session; no cross-company rows can appear.
- **No PII**: responses contain only counts, rates, scores, and durations.
- **Performance (SC-004)**: both endpoints target p95 ≤ 300 ms, computed on read.
