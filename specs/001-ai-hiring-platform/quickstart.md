# Quickstart Validation Guide: HireIQ MVP

**Feature**: 001-ai-hiring-platform | **Date**: 2026-06-04

This guide documents how to validate each user story end-to-end once the platform is running. It is a validation reference — not an implementation guide. For full API details see [contracts/api.md](contracts/api.md) and [contracts/websocket.md](contracts/websocket.md). For entity definitions see [data-model.md](data-model.md).

---

## Prerequisites

- Docker and Docker Compose installed
- OpenAI API key with access to `gpt-4o`, `whisper-1`, and `tts-1`
- Azure credentials (optional for local dev — fallback storage and OCR are used automatically)
- Ports 3000, 5432, 6379, 8000, 8001, 8200 available

---

## Setup

```bash
# Clone and start all services
git clone <repo-url>
cd HireIQ
cp infra/.env.example infra/.env   # fill in OPENAI_API_KEY at minimum

docker compose -f infra/docker-compose.yml up -d

# Wait for services to be ready (postgres + migrations complete)
docker compose -f infra/docker-compose.yml logs -f api | grep "Application startup complete"

# Verify health endpoints
curl http://localhost:8000/health    # api service
curl http://localhost:8001/health    # agents service
```

Expected health response:
```json
{ "status": "ok", "db": "ok", "redis": "ok", "agents": "ok" }
```

---

## Story 1: Recruiter Sets Up a Job with AI-Guided Criteria

**Goal**: Create a company + admin, create a job, complete the setup conversation, and verify the job is `active`.

```bash
# Register company and admin
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"company_name": "Acme Corp", "email": "admin@acme.com", "password": "secret123"}'
# Save access_token from response as $TOKEN

# Create a job
curl -X POST http://localhost:8000/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Senior Backend Engineer"}'
# Save job id as $JOB_ID

# Advance the setup conversation (repeat until status = "completed")
curl -X POST http://localhost:8000/jobs/$JOB_ID/setup/turn \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "We need strong Python and PostgreSQL skills, 3+ years experience."}'

# Continue responding to AI questions until criteria_draft is non-null and status = "completed"

# Activate the job
curl -X POST http://localhost:8000/jobs/$JOB_ID/activate \
  -H "Authorization: Bearer $TOKEN"
```

**Expected outcome**: `GET /jobs/$JOB_ID` returns `"status": "active"` with a non-null `criteria` block. Job appears on `GET /jobs` list.

**Acceptance check** (SC-001): The full sequence — register to active job — should complete under 15 minutes.

---

## Story 2: Candidate Applies and Gets Screened

**Goal**: Submit a PDF CV to the active job and verify a screening result appears within 2 minutes.

```bash
# Submit application (no auth required)
curl -X POST http://localhost:8000/jobs/$JOB_ID/applications \
  -F "full_name=Jane Doe" \
  -F "email=jane@example.com" \
  -F "cv=@/path/to/test-cv.pdf"
# Save application_id as $APP_ID

# Poll until screening is complete (typically < 2 min)
watch -n 10 "curl -s -H 'Authorization: Bearer $TOKEN' \
  http://localhost:8000/applications/$APP_ID | jq '.screening_status, .screening_score'"
```

**Expected outcome**:
- `screening_status` transitions from `pending` → `qualified` or `rejected`
- `screening_score` is a number 0–100
- `screening_rationale` is a non-empty string
- Candidate receives a confirmation email (check mail container or configured SMTP)

**Scanned PDF test**: Submit a scan-only PDF (no embedded text). Expected: `cv_extraction_method` = `"document_intelligence"` and screening still completes successfully.

**Duplicate test**: Re-submit with the same email to the same job. Expected: `409 Conflict`.

**Corrupt PDF test**: Submit a password-protected or truncated PDF. Expected: `422 Unprocessable Entity` with a clear error message; no application record created.

---

## Story 3: Candidate Completes a Voice Interview

**Goal**: Invite a qualified candidate, have them complete a WebSocket voice interview, and verify the full transcript is stored.

```bash
# Invite the qualified candidate (recruiter action)
curl -X POST http://localhost:8000/applications/$APP_ID/invite \
  -H "Authorization: Bearer $TOKEN"
# Save interview_token from the invitation email or by reading applications/$APP_ID

# Connect to the interview via WebSocket (use wscat or a browser)
npx wscat -c ws://localhost:8000/interviews/$INTERVIEW_TOKEN/connect
```

After connecting, the server sends `session_ready`. Then exchange turns:

```json
# Server → Client (session_ready)
{"type":"session_ready","session_id":"...","mode":"voice","turn_count":0,"max_turns":20,"resuming":false}

# Client → Server (text_input for automated testing)
{"type":"text_input","content":"I have 6 years of Python experience, including building high-throughput data pipelines."}

# Server → Client (turn_processing, then ai_turn)
{"type":"ai_turn","turn_index":1,"text":"Interesting — can you describe the most complex pipeline you've built?","audio":"<base64>","dimensions_remaining":2}
```

Continue until `{"type":"interview_complete"}` is received.

**Expected outcome**:
- `GET /evaluations` for the job shows the candidate after evaluation completes (≤ 5 min post-interview, SC-004)
- Each turn stored in `interview_messages` with correct `turn_index` and `speaker`
- AI turns have `content_text` (PII-redacted)

**Resume test**: Disconnect mid-interview, wait 30 seconds, reconnect with the same token. Expected: `session_ready` with `"resuming": true` and `turn_count > 0`.

**Expired link test**: Use an expired token. Expected: WebSocket connection closed with code `1008`.

**Guardrail test**: Send a harmful or completely off-topic message. Expected: server sends `turn_blocked`; the candidate's message does not appear in the stored transcript.

---

## Story 4: Recruiter Reviews Evaluations and Shortlists

**Goal**: Verify the ranked shortlist and full evaluation detail are accessible after interview completion.

```bash
# Ranked shortlist
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/jobs/$JOB_ID/evaluations

# Full evaluation detail (replace $EVAL_ID with id from shortlist)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/evaluations/$EVAL_ID
```

**Expected outcome**:
- Shortlist is ordered by `overall_score DESC`
- Full evaluation includes `dimension_scores` with at least one `evidence_quotes` entry per dimension
- `consistency_flags` is present (may be empty)
- `communication_quality` contains all three metrics
- If interview had low-quality responses: `confidence_flag: true` with a non-null `confidence_reason`
- Audio playback: `GET /evaluations/$EVAL_ID/transcript/{turn_index}/audio` returns `audio/mpeg` for candidate turns

---

## Story 5: Candidate Receives a Feedback Report

**Goal**: Verify the candidate receives a feedback email and can access the feedback report without an account.

After evaluation completes, the candidate receives an email with a feedback link. The link contains a `feedback_token`.

```bash
# Access the feedback report (no auth)
curl http://localhost:8000/feedback/$FEEDBACK_TOKEN
```

**Expected outcome**:
- Response includes `dimension_scores` and `summary` (strengths + areas for improvement)
- `recommendation` (hire/no-hire) is NOT present in the response
- No other candidates' data is visible
- Accessing an expired or invalid token returns `410 Gone` or `404 Not Found`

**Timing check** (SC-001 → FR-031): Feedback email arrives within 30 minutes of interview completion.

---

## Tenant Isolation Validation

**Goal**: Verify Company A cannot see Company B's data.

```bash
# Register Company B with its own admin
curl -X POST http://localhost:8000/auth/register \
  -d '{"company_name": "BetaCo", "email": "admin@betaco.com", "password": "secret456"}'
# Save token as $TOKEN_B

# Attempt to access Company A's job with Company B's token
curl -H "Authorization: Bearer $TOKEN_B" \
  http://localhost:8000/jobs/$JOB_ID   # $JOB_ID belongs to Company A
```

**Expected outcome**: `404 Not Found` (RLS makes Company A's rows invisible to Company B's session, not `403 Forbidden` — the row is simply not found).

---

## CI Smoke Test

The above scenarios map directly to integration test cases in `backend/tests/integration/`. Run them with:

```bash
docker compose -f infra/docker-compose.yml run --rm api pytest tests/integration/ -v
```

All five stories must pass before merging to `main`.
