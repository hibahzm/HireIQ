# REST API Contract: HireIQ API Service

**Service**: `backend/` | **Base URL**: `http://localhost:8000` (local), `https://api.<env>.hireiq.io` (Azure)

**Auth**: Bearer token (access JWT) in `Authorization` header for all authenticated endpoints.

Response envelope for errors:
```json
{ "detail": "<message>" }
```

---

## Health

### `GET /health`

Public. Returns machine-readable status for Container Apps readiness probe.

**Response 200**:
```json
{
  "status": "ok",
  "db": "ok",
  "redis": "ok",
  "agents": "ok"
}
```
`status` is `"degraded"` if any dependency is unreachable; HTTP status stays 200 for partial degradation (Container Apps keeps routing); returns 503 only if the service itself cannot serve traffic.

---

## Auth

### `POST /auth/register`

Public. Creates a company and its first admin user.

**Request**:
```json
{
  "company_name": "Acme Corp",
  "email": "admin@acme.com",
  "password": "s3cur3passw0rd"
}
```

**Response 201**:
```json
{
  "company_id": "uuid",
  "user_id": "uuid",
  "access_token": "jwt",
  "token_type": "bearer"
}
```
Refresh token set as `HttpOnly; Secure; SameSite=Strict` cookie.

**Errors**: `409` if email already registered.

---

### `POST /auth/login`

Public.

**Request**:
```json
{ "email": "recruiter@acme.com", "password": "..." }
```

**Response 200**:
```json
{ "access_token": "jwt", "token_type": "bearer" }
```
Refresh token set as cookie.

**Errors**: `401` on invalid credentials.

---

### `POST /auth/refresh`

Public (uses cookie). Issues new access token + new refresh token; invalidates old refresh token in Redis.

**Response 200**:
```json
{ "access_token": "jwt", "token_type": "bearer" }
```

**Errors**: `401` if refresh token invalid, expired, or already used.

---

### `POST /auth/logout`

Authenticated. Invalidates refresh token.

**Response 204**: No content.

---

## Companies

### `GET /companies/me`

Authenticated (any role).

**Response 200**:
```json
{
  "id": "uuid",
  "name": "Acme Corp",
  "created_at": "2026-06-04T00:00:00Z"
}
```

---

### `PUT /companies/me`

Authenticated (admin only).

**Request**: `{ "name": "Acme Corp Renamed" }`

**Response 200**: Updated company object.

---

## Jobs

### `GET /jobs`

Authenticated (any role). Lists all jobs for the current company.

**Query params**: `?status=active` (optional filter by status)

**Response 200**:
```json
[
  {
    "id": "uuid",
    "title": "Senior Backend Engineer",
    "status": "active",
    "application_count": 42,
    "created_at": "2026-06-04T00:00:00Z",
    "updated_at": "2026-06-04T00:00:00Z"
  }
]
```

---

### `POST /jobs`

Authenticated (recruiter/admin).

**Request**: `{ "title": "Senior Backend Engineer" }`

**Response 201**:
```json
{
  "id": "uuid",
  "title": "Senior Backend Engineer",
  "status": "draft",
  "created_at": "2026-06-04T00:00:00Z"
}
```

---

### `GET /jobs/{job_id}`

Authenticated (any role). Returns job with criteria if available.

**Response 200**:
```json
{
  "id": "uuid",
  "title": "Senior Backend Engineer",
  "status": "active",
  "criteria": {
    "required_skills": [{"skill": "Python", "priority": "required"}],
    "optional_skills": [],
    "experience_level": "senior",
    "min_years_experience": 5,
    "evaluation_dimensions": [
      {"name": "Technical Depth", "weight": 0.4, "description": "..."},
      {"name": "System Design", "weight": 0.3, "description": "..."},
      {"name": "Communication", "weight": 0.3, "description": "..."}
    ],
    "dealbreakers": ["No Python experience"],
    "min_screening_score": 60
  }
}
```
`criteria` is `null` if job status is `draft`.

---

### `PUT /jobs/{job_id}`

Authenticated (recruiter/admin). Updates title or triggers status transitions (`paused` ↔ `active`, `active → closed`).

**Request**: `{ "title": "...", "status": "paused" }` (either field optional)

**Response 200**: Updated job object.

**Errors**: `422` for invalid status transitions.

---

### `POST /jobs/{job_id}/setup/turn`

Authenticated (recruiter/admin). Advances the AI-guided setup conversation by one turn.

**Request**:
```json
{ "message": "We need strong Python and PostgreSQL skills, ideally 3+ years." }
```

**Response 200**:
```json
{
  "message": "Got it! Should these be hard requirements or nice-to-haves?",
  "status": "in_progress",
  "criteria_draft": null
}
```
When setup is complete:
```json
{
  "message": "I've captured the criteria. Here's the summary — confirm to activate the job.",
  "status": "completed",
  "criteria_draft": { ... }
}
```
Calling `/jobs/{job_id}` with `?activate=true` after `status: completed` transitions job to `active`.

**Errors**: `409` if job already has completed criteria; `404` if job not found.

---

### `POST /jobs/{job_id}/activate`

Authenticated (recruiter/admin). Transitions job from `setup` to `active` after criteria are confirmed.

**Response 200**: Updated job object with `status: "active"`.

**Errors**: `409` if setup conversation not completed.

---

## Applications

### `POST /jobs/{job_id}/applications`

**Public** (no auth required — candidates apply without accounts).

**Request** (`multipart/form-data`):
- `full_name: string`
- `email: string`
- `cv: file (PDF, max 10 MB)`

**Response 201**:
```json
{
  "application_id": "uuid",
  "message": "Application received. Check your email for confirmation."
}
```

**Errors**:
- `409` if this email already applied to this job
- `422` if CV is corrupted, password-protected, or unreadable after extraction attempts
- `422` if job is not `active`
- `429` if rate limit exceeded (5 uploads per IP per hour)

---

### `GET /jobs/{job_id}/applications`

Authenticated (any role). Lists applications for a job with screening results.

**Query params**: `?status=qualified&page=1&page_size=25`

**Response 200**:
```json
{
  "items": [
    {
      "id": "uuid",
      "candidate": { "full_name": "Jane Doe", "email": "jane@example.com" },
      "screening_score": 82,
      "screening_status": "qualified",
      "status": "evaluated",
      "created_at": "2026-06-04T00:00:00Z"
    }
  ],
  "total": 120,
  "page": 1,
  "page_size": 25
}
```

---

### `GET /applications/{application_id}`

Authenticated (any role). Returns full application detail including screening rationale.

**Response 200**:
```json
{
  "id": "uuid",
  "job_id": "uuid",
  "candidate": { "full_name": "Jane Doe", "email": "jane@example.com" },
  "cv_extraction_method": "pymupdf",
  "screening_score": 82,
  "screening_rationale": "Candidate demonstrates strong Python experience...",
  "screening_status": "qualified",
  "status": "evaluated",
  "interview_token_expires_at": "2026-06-11T00:00:00Z",
  "created_at": "2026-06-04T00:00:00Z"
}
```

---

### `POST /applications/{application_id}/invite`

Authenticated (recruiter/admin). Sends interview invitation email; sets `interview_token` and `interview_token_expires_at` (7 days).

**Response 200**:
```json
{
  "message": "Invitation sent",
  "interview_token_expires_at": "2026-06-11T00:00:00Z"
}
```

**Errors**: `409` if already invited; `422` if application not in `qualified` status.

---

## Evaluations

### `GET /jobs/{job_id}/evaluations`

Authenticated (any role). Returns ranked shortlist for a job, ordered by `overall_score DESC`.

**Response 200**:
```json
[
  {
    "evaluation_id": "uuid",
    "application_id": "uuid",
    "candidate": { "full_name": "Jane Doe" },
    "overall_score": 88,
    "recommendation": "hire",
    "confidence_flag": false,
    "created_at": "2026-06-04T00:00:00Z"
  }
]
```

---

### `GET /evaluations/{evaluation_id}`

Authenticated (any role). Full evaluation detail.

**Response 200**:
```json
{
  "id": "uuid",
  "application_id": "uuid",
  "overall_score": 88,
  "recommendation": "hire",
  "dimension_scores": [
    {
      "dimension": "Technical Depth",
      "score": 90,
      "evidence_quotes": ["Described a sharding strategy for a 500M-row table..."]
    }
  ],
  "consistency_flags": [
    {
      "claim": "Led team of 10 engineers",
      "cv_statement": "Team lead at Company X",
      "interview_statement": "I was one of several leads",
      "flag_type": "contradiction"
    }
  ],
  "communication_quality": {
    "response_depth": 0.82,
    "filler_word_frequency": 0.03,
    "deflection_frequency": 0.05
  },
  "confidence_flag": false,
  "confidence_reason": null,
  "transcript": [
    {
      "turn_index": 0,
      "speaker": "ai",
      "content_text": "Tell me about your experience with distributed systems.",
      "audio_url": null
    },
    {
      "turn_index": 1,
      "speaker": "candidate",
      "content_text": "I led the design of a Kafka-based event pipeline...",
      "audio_url": "/evaluations/uuid/transcript/1/audio"
    }
  ]
}
```

---

### `GET /evaluations/{evaluation_id}/transcript/{turn_index}/audio`

Authenticated (any role). Streams audio recording for a specific turn.

**Response 200**: `audio/mpeg` stream.

**Errors**: `404` if no audio for this turn; `403` if tenant mismatch.

---

## Feedback (Public — no auth)

### `GET /feedback/{token}`

Public. Returns candidate feedback report via secure token. Token is single-use for 30 days.

**Response 200**:
```json
{
  "job_title": "Senior Backend Engineer",
  "overall_score": 88,
  "dimension_scores": [
    { "dimension": "Technical Depth", "score": 90 },
    { "dimension": "Communication", "score": 75 }
  ],
  "summary": {
    "strengths": "Strong systems design knowledge...",
    "areas_for_improvement": "Could improve conciseness in responses..."
  }
}
```

**Errors**: `404` if token invalid; `410` if token expired.

Note: No candidate PII from other applicants is exposed. No `recommendation` field is returned (hire/no-hire is internal to the recruiter).
