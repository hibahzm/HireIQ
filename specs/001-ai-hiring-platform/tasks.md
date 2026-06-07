# Tasks: HireIQ — AI-Powered Hiring Platform (MVP + V2)

**Input**: Design documents from `specs/001-ai-hiring-platform/`

**Prerequisites**: [plan.md](plan.md) · [spec.md](spec.md) · [data-model.md](data-model.md) · [contracts/](contracts/) · [research.md](research.md) · [quickstart.md](quickstart.md)

**Tests**: Test tasks are included for the four domains where the constitution (Principle VIII) mandates TDD: auth/authorization, CV screening pipeline, voice interview turn handling, and evaluation pipeline. These tests MUST be written and confirmed failing before the corresponding implementation tasks begin.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared in-progress dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Exact file paths are included in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the monorepo, initialize all three projects, wire up CI/CD skeleton, and lock the .gitignore before any code is written.

- [x] T001 Create monorepo directory structure: `backend/`, `agents/`, `frontend/`, `infra/`, `.github/workflows/` at repo root
- [x] T002 [P] Initialize `backend/` Python project — `pyproject.toml` with all api service dependencies (fastapi, sqlalchemy[asyncio], asyncpg, alembic, python-jose[cryptography], bcrypt, httpx, redis[asyncio], azure-storage-blob, PyMuPDF, azure-ai-formrecognizer, openai, azure-identity, hvac, structlog), ruff config, pytest config
- [x] T003 [P] Initialize `agents/` Python project — `pyproject.toml` with agents service dependencies (fastapi, langgraph, langchain-openai, openai, structlog), ruff config, pytest config
- [x] T004 [P] Initialize `frontend/` project — `npm create vite@latest` with React + TypeScript template; install tailwindcss, postcss, autoprefixer; configure `tailwind.config.ts`; install `@axe-core/react` as a dev dependency for accessibility auditing (M7)
- [x] T005 Create `infra/docker-compose.yml` defining 6 services: `api` (backend, port 8000), `agents` (agents service, port 8001, internal-only), `frontend` (nginx, port 3000), `postgres` (postgres:16 with pgvector, port 5432), `redis` (redis:7, port 6379), `vault` (vault:1.15, dev mode, port 8200)
- [x] T006 [P] Configure GitHub Actions CI workflow in `.github/workflows/ci.yml` — lint (ruff) and test (pytest) for backend and agents on every push; frontend type-check and build
- [x] T007 [P] Create `.gitignore` at repo root and within `backend/` and `agents/` covering `.env*`, `*.pem`, `*.key`, `*.p12`, model weight directories, `__pycache__`, `dist/`, `.venv/`, `node_modules/` (Principle IV)
- [x] T007a [P] Write multi-stage `Dockerfile` for `backend/` in `backend/Dockerfile` — builder stage installs deps from `pyproject.toml`; runtime stage uses `python:3.12-slim`, non-root `app` user, copies built packages, exposes port 8000, adds `HEALTHCHECK` (research §8 pattern)
- [x] T007b [P] Write multi-stage `Dockerfile` for `agents/` in `agents/Dockerfile` — same pattern as T007a; exposes port 8001
- [x] T007c [P] Write `Dockerfile` for `frontend/` in `frontend/Dockerfile` — builder stage runs `npm run build`; runtime stage uses `nginx:alpine`, copies `dist/` to `/usr/share/nginx/html`, copies `infra/nginx.conf`

**Checkpoint**: All three projects scaffold successfully; `docker compose up` starts all 6 services without errors; CI pipeline runs on push; `docker build` succeeds for all three services.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure that every user story depends on. No feature work can begin until this phase is complete.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T008 Implement `backend/app/config.py` — `Settings` class using `pydantic-settings`; reads secrets from HashiCorp Vault in dev (via `hvac`) and Azure Key Vault in production (via `azure-identity` `DefaultAzureCredential`); covers `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `JWT_SECRET`, `AGENTS_INTERNAL_SECRET`, `STORAGE_*`, `VAULT_ADDR`, `EMAIL_API_KEY`, `EMAIL_FROM`, `EMAIL_BACKEND` (console | resend)
- [x] T009 [P] Implement `agents/app/config.py` — same Vault/Azure Key Vault pattern; covers `OPENAI_API_KEY`, `AGENTS_INTERNAL_SECRET`, `AZURE_SPEECH_*`
- [x] T010 Create initial Alembic migration in `backend/alembic/versions/` — enable pgvector extension; create `companies` and `users` tables with all columns from data-model.md; add standard tenant RLS policy on `users`; configure Alembic `env.py` with BYPASSRLS migration user
- [x] T011 Implement async SQLAlchemy engine in `backend/app/db.py` — `create_async_engine` with asyncpg; `Base` declarative base; `_get_session_factory()` raw factory used by services and background tasks; `get_db(company_id)` low-level async generator; RLS (`SET LOCAL app.current_company_id`) is enforced by `get_authed_session` in `deps.py` (T028) for routes, and set manually in background tasks (research §1 pattern)
- [x] T012 [P] Implement Redis async client setup in `backend/app/redis_client.py` — `aioredis.from_url()`; expose `get_redis()` dependency
- [x] T013 [P] Implement `StorageService` in `backend/app/services/storage_service.py` — `upload(key, data)`, `download(key)`, `delete(key)`; uses `azure-storage-blob` `BlobServiceClient` in production; writes to local `./storage/` directory when `STORAGE_BACKEND=local` (dev default)
- [x] T014 Configure structlog with correlation ID middleware in `backend/app/middleware/logging.py` — attach `request_id` (UUID from header or generated) to every log entry; bind `company_id` when available; JSON output in production, colored console in dev
- [x] T015 [P] Configure structlog for `agents/` in `agents/app/middleware/logging.py` — same pattern; bind `session_id` and `agent_type` to log context
- [x] T016 Implement `GuardRegistry` and `PIIRedactor` in `agents/app/guardrails/registry.py` and `agents/app/guardrails/pii_redactor.py` — `registry.check_input(text, context)` and `registry.check_output(text, context)` must wrap every LLM call (Principle V); `PIIRedactor.redact(text)` strips names, emails, phone numbers before any response is returned to the api service; returns `GuardResult(passed, reason)`
- [x] T017 Create Alembic migration for `audit_logs` table; implement `AuditLogRepository` in `backend/app/repositories/audit_log_repository.py` — append-only `log_event(event_type, entity_type, entity_id, metadata, company_id, actor_id, actor_type)` async method; no UPDATE/DELETE (Principle VII)
- [x] T018 [P] Implement `/health` endpoint for backend in `backend/app/api/routers/health.py` — checks DB connectivity, Redis ping, agents service `/health`; returns `{status, db, redis, agents}` (Principle VII)
- [x] T019 [P] Implement `/health` endpoint for agents in `agents/app/api/routers/health.py` — checks OpenAI reachability; returns `{status}`
- [x] T020 Implement `backend/app/main.py` and `agents/app/main.py` — FastAPI app instantiation; register all routers; add `X-Internal-Secret` validation middleware to agents service (rejects requests without the shared secret); add logging middleware; add CORS for frontend origin

**Checkpoint**: Both services start and return `{"status": "ok"}` from `/health`. `get_db()` correctly sets `app.current_company_id` and rolls back on error. Guardrail registry blocks a test toxic input and passes a benign one.

---

## Phase 3: User Story 1 — Recruiter Sets Up a Job with AI-Guided Criteria (Priority: P1) 🎯 MVP

**Goal**: Company registration, user auth, job creation, AI-guided setup conversation, job activation.

**Independent Test**: Register a company, create a job, complete the setup conversation with the AI, activate the job. `GET /jobs/{id}` returns `status: "active"` with non-null `criteria`. See [quickstart.md §Story 1](quickstart.md).

### Tests for User Story 1 (constitution-mandated — write FIRST, confirm FAILING before T026)

- [x] T021 [P] [US1] Write failing integration test: company registration + admin user creation in `backend/tests/integration/test_auth.py` — asserts 201 response, access token returned, refresh cookie set
- [x] T022 [P] [US1] Write failing integration test: login → access token valid → refresh → old token rejected → logout in `backend/tests/integration/test_auth.py` — verifies token rotation (research §5)

### Implementation for User Story 1

- [x] T023 [P] [US1] Create Alembic migration for `jobs`, `job_criteria`, `setup_conversations` tables with all columns from data-model.md; add RLS policies; add `(company_id, status)` index on jobs
- [x] T024 [P] [US1] Implement SQLAlchemy ORM models: `Company` in `backend/app/models/company.py`, `User` in `backend/app/models/user.py` — all columns from data-model.md
- [x] T025 [US1] Implement `CompanyRepository` and `UserRepository` in `backend/app/repositories/company_repository.py` and `backend/app/repositories/user_repository.py` — async CRUD; UserRepository includes `get_by_email_global()` that bypasses RLS for login lookup
- [x] T026 [US1] Implement `AuthService` in `backend/app/services/auth_service.py` — `register(company_name, email, password)`, `login(email, password)`, `refresh(token)`, `logout(token)`; HS256 JWT (15 min access / 7 day refresh); bcrypt password hashing; refresh token rotation via Redis `refresh_token:{hash}` key (research §5)
- [x] T027 [US1] Implement auth router in `backend/app/api/routers/auth.py` — `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`; set HttpOnly Secure SameSite=Strict cookie for refresh token
- [x] T028 [US1] Implement FastAPI `Depends()` wiring in `backend/app/api/deps.py` — `get_current_user()` (decodes JWT, loads User in its own short-lived session), `require_admin()`, `require_recruiter_or_admin()`; `get_authed_session()` (yields an `AsyncSession` with `SET LOCAL app.current_company_id` already applied — this is the RLS-safe session used by all authenticated routes; FastAPI deduplicates `get_current_user` so it runs once per request even when both `require_*` and `get_authed_session` appear)
- [x] T029 [P] [US1] Implement SQLAlchemy ORM models: `Job` in `backend/app/models/job.py`, `JobCriteria` in `backend/app/models/job_criteria.py`, `SetupConversation` in `backend/app/models/setup_conversation.py`
- [x] T030 [US1] Implement `JobRepository` and `SetupConversationRepository` in `backend/app/repositories/` — async CRUD; JobRepository includes `list_by_company(status_filter)` for dashboard
- [x] T031 [US1] Implement `job_setup_graph` LangGraph `StateGraph` in `agents/app/graphs/job_setup_graph.py` — nodes: `elicit_criteria`, `confirm_criteria`; state: `{conversation_history, criteria_draft, status}`; every LLM call guarded by `registry.check_input` and `registry.check_output`; PII-redact output before returning
- [x] T032 [US1] Implement `/agents/job-setup/turn` endpoint in `agents/app/api/routers/job_setup.py` — receives `{job_id, company_id, conversation_history, user_message}`; invokes `job_setup_graph`; returns `{message, status, criteria_draft}`
- [x] T033 [US1] Implement `JobService` in `backend/app/services/job_service.py` — `create_job(title)`, `advance_setup(job_id, user_message)` (calls agents service via httpx.AsyncClient, persists conversation, transitions job to `setup`), `activate_job(job_id)` (validates criteria complete, transitions to `active`, embeds job chunks via `EmbeddingService`); log all transitions to `audit_log`
- [x] T034 [US1] Implement job router in `backend/app/api/routers/jobs.py` — `GET /jobs`, `POST /jobs`, `GET /jobs/{id}`, `PUT /jobs/{id}`, `POST /jobs/{id}/setup/turn`, `POST /jobs/{id}/activate`; all endpoints use `require_recruiter_or_admin()`
- [x] T035 [US1] Implement `JobListPage` in `frontend/src/pages/jobs/JobListPage.tsx` — displays jobs table with status badges; links to job detail and setup; requires auth
- [x] T036 [P] [US1] Implement `JobSetupPage` in `frontend/src/pages/jobs/JobSetupPage.tsx` — chat-style interface for the setup conversation; shows criteria summary when status = `completed`; confirm button calls `/activate`
- [x] T037 [P] [US1] Implement `LoginPage` in `frontend/src/pages/auth/LoginPage.tsx` and `RegisterPage` in `frontend/src/pages/auth/RegisterPage.tsx` — forms with validation; store access token in memory; configure `api.ts` typed client in `frontend/src/services/api.ts`
- [x] T037a [US1] Add `GET /users`, `POST /users`, `DELETE /users/{id}`, `PUT /users/{id}/role` endpoints to a new `backend/app/api/routers/users.py` — all require `require_admin()`; `GET /users` lists all users in the current company; `POST /users` creates a recruiter account (sends invite email via `NotificationService`); `PUT /users/{id}/role` changes role between admin/recruiter; `DELETE /users/{id}` soft-deactivates (sets `is_active=False`) (FR-003, C1)
- [x] T037b [US1] Add `list_by_company()`, `create_user()`, `set_role()`, `deactivate()` methods to `UserRepository` in `backend/app/repositories/user_repository.py` (supports T037a)
- [x] T037c [US1] Implement `UserManagementPage` in `frontend/src/pages/company/UserManagementPage.tsx` — admin-only page; lists company users with role badge and active/inactive status; invite new recruiter form (email + role); deactivate button; role change dropdown (FR-003, C1)

**Checkpoint**: Full job setup flow works end-to-end. Auth tests T021/T022 pass. Job is `active` after confirming criteria. Tenant isolation: Company B token returns 404 on Company A job.

---

## Phase 4: User Story 2 — Candidate Applies and Gets Screened (Priority: P2)

**Goal**: Public application form, CV upload, OCR extraction, hybrid vector search, LLM screening, confirmation email, recruiter screening view.

**Independent Test**: Submit a PDF CV to an active job; within 2 minutes `GET /applications/{id}` shows `screening_status: "qualified"` or `"rejected"` with a score and rationale. See [quickstart.md §Story 2](quickstart.md).

### Tests for User Story 2 (constitution-mandated — write FIRST, confirm FAILING before T049)

- [x] T038 [P] [US2] Write failing integration test: full CV screening pipeline (upload → OCR → embed → guardrails → agent → result stored) in `backend/tests/integration/test_screening.py` — mocks LLM calls; asserts `screening_score` and `screening_rationale` are set and PII-redacted
- [x] T039 [P] [US2] Write failing integration test: duplicate application rejection (same email + same job → 409) and corrupt PDF rejection (422, no application record created) in `backend/tests/integration/test_applications.py`

### Implementation for User Story 2

- [x] T040 [P] [US2] Create Alembic migration for `candidates`, `applications`, `cv_chunks`, `job_chunks` tables; add `UNIQUE (job_id, candidate_id)` on applications; add ivfflat index on `cv_chunks.embedding` (lists=100), GIN index on `cv_chunks.tsv`; add ivfflat index on `job_chunks.embedding` (lists=50); add RLS policies on all four tables (research §3)
- [x] T041 [P] [US2] Implement SQLAlchemy ORM models: `Candidate` in `backend/app/models/candidate.py`, `Application` in `backend/app/models/application.py`
- [x] T042 [P] [US2] Implement SQLAlchemy ORM models: `CvChunk` in `backend/app/models/cv_chunk.py`, `JobChunk` in `backend/app/models/job_chunk.py` — `embedding` column as `Vector(1536)` using `pgvector.sqlalchemy`
- [x] T043 [US2] Implement `CandidateRepository` and `ApplicationRepository` in `backend/app/repositories/` — async CRUD; ApplicationRepository includes `get_by_job_and_email(job_id, email)` for duplicate check and `list_by_job(job_id, status_filter, page, page_size)` for recruiter dashboard
- [x] T044 [US2] Implement `CvChunkRepository` and `JobChunkRepository` in `backend/app/repositories/` — async bulk insert; `hybrid_search(job_id, query_embedding, query_text, top_k=20)` that runs dense cosine and sparse tsvector queries via `asyncio.gather`, then applies RRF (k=60) to merge and return top 10 results (research §3)
- [x] T045 [US2] Implement `OcrService` in `backend/app/services/ocr_service.py` — try PyMuPDF `fitz.open()`; if `word_count < 50` OR `printable_ratio < 0.90` fall back to Azure Document Intelligence `prebuilt-document`; raise `ValidationError` if file is corrupted/encrypted (research §10)
- [x] T046 [US2] Implement `EmbeddingService` in `backend/app/services/embedding_service.py` — `embed_text(text)` via OpenAI `text-embedding-3-small`; `chunk_cv(cv_text)` splits text into overlapping 512-token chunks; returns list of `(chunk_text, embedding)` tuples
- [x] T047 [US2] Implement `screening_graph` LangGraph `StateGraph` in `agents/app/graphs/screening_graph.py` — node: `score_cv`; input guarded by `registry.check_input`; output PII-redacted before return; scores 0–100 against job criteria using hybrid search results as context
- [x] T048 [US2] Implement `/agents/cv-screen` endpoint in `agents/app/api/routers/screening.py` — receives `{application_id, company_id, cv_text, job_criteria, hybrid_search_results}`; invokes `screening_graph`; returns `{score, rationale, status, guardrail_triggered}`
- [x] T049 [US2] Implement `ScreeningService` in `backend/app/services/screening_service.py` — orchestrates: validate CV → OCR → chunk + embed → store chunks → hybrid search → call agents `/cv-screen` → persist score/rationale/status on application → log to audit_log
- [x] T050 [US2] Implement `NotificationService` in `backend/app/services/notification_service.py` — `send_confirmation_email(candidate_email, job_title)`, `send_invitation_email(candidate_email, interview_link)`, `send_feedback_email(candidate_email, feedback_link)`; uses Resend SDK (`resend` package) when `EMAIL_BACKEND=resend`, logs to stdout when `EMAIL_BACKEND=console` (dev default); uses Redis email dedup key `email:dedup:{template}:{recipient}:{day}` TTL 24h (research §4)
- [x] T051 [US2] Implement applications router in `backend/app/api/routers/applications.py` — `POST /jobs/{id}/applications` (public, multipart, rate-limited 5/IP/hr via Redis `ratelimit:cv:{ip_hash}`), `GET /jobs/{id}/applications` (recruiter auth), `GET /applications/{id}` (recruiter auth), `POST /applications/{id}/invite` (recruiter auth, sets `interview_token` UUID + 7-day expiry, calls `NotificationService.send_invitation_email`)
- [x] T052 [US2] Implement `JobApplicationPage` in `frontend/src/pages/applications/JobApplicationPage.tsx` — public form (no auth); fields: full_name, email, CV file upload (PDF only, max 10 MB); shows success confirmation and error states
- [x] T053 [P] [US2] Implement `ApplicationListPage` in `frontend/src/pages/applications/ApplicationListPage.tsx` — recruiter view; lists applications with score badge, status chip (`qualified`, `rejected`, `screening`, `system_interrupted` shown distinctly from `abandoned` per FR-020b), and invite button for qualified candidates
- [x] T053a [US2] Implement `ApplicationDetailPage` in `frontend/src/pages/applications/ApplicationDetailPage.tsx` — recruiter view for a single application; shows candidate name/email, CV extraction method, screening score with rationale, current status (including `system_interrupted` vs `abandoned` distinction), and invite button; linked from `ApplicationListPage` row (FR-014, M5)

**Checkpoint**: CV upload → screening completes within 2 min. Screening pipeline tests T038/T039 pass. Scanned PDF uses Document Intelligence fallback. Duplicate application returns 409. Corrupt PDF returns 422 with no DB record created.

---

## Phase 5: User Story 3 — Candidate Completes a Voice Interview (Priority: P3)

**Goal**: WebSocket voice interview with STT/TTS, turn sequencing, session resume, guardrail blocking, system interruption handling.

**Independent Test**: Candidate opens invitation link, completes voice interview, sees completion screen. Full transcript stored. Session resumes after simulated disconnect. See [quickstart.md §Story 3](quickstart.md).

### Tests for User Story 3 (constitution-mandated — write FIRST, confirm FAILING before T063)

- [x] T054 [P] [US3] Write failing integration test: WebSocket interview turn sequence — connect → send text_input → receive ai_turn → repeat → receive interview_complete in `backend/tests/integration/test_interview.py` — mocks agents service and TTS; asserts all messages stored; final status `completed`
- [x] T055 [P] [US3] Write failing integration test: session resume (disconnect after turn 3, reconnect within 24h → `resuming: true`, turn_count = 3) and expiry (reconnect after 24h → `session_expired` message and WS close 1008) in `backend/tests/integration/test_interview_resume.py`

### Implementation for User Story 3

- [x] T056 [P] [US3] Create Alembic migration for `interview_sessions`, `interview_messages` tables with all columns from data-model.md; add `UNIQUE (session_id, turn_index)` on interview_messages; add RLS policies
- [x] T057 [P] [US3] Implement SQLAlchemy ORM models: `InterviewSession` in `backend/app/models/interview_session.py`, `InterviewMessage` in `backend/app/models/interview_message.py`
- [x] T058 [US3] Implement `InterviewSessionRepository` and `InterviewMessageRepository` in `backend/app/repositories/` — async CRUD; `get_by_interview_token(token)` on applications bypasses RLS (token is the authenticator); `append_message(session_id, turn_index, speaker, content_text, audio_blob_key, is_blocked)`
- [x] T059 [US3] Implement `SttService` in `backend/app/services/stt_service.py` — `transcribe(audio_bytes, filename)` via OpenAI `whisper-1`; returns transcript text; raises on empty/noise audio
- [x] T060 [US3] Implement `TtsService` in `backend/app/services/tts_service.py` — `synthesize(text)` via OpenAI `tts-1` (voice: `onyx`); falls back to Azure AI Speech if OpenAI TTS fails; returns MP3 bytes
- [x] T061 [US3] Implement `interview_graph` LangGraph `StateGraph` in `agents/app/graphs/interview_graph.py` — nodes: `check_input_guard`, `generate_response`, `check_output_guard`; state: `InterviewState` (conversation_history, dimensions_covered, dimensions_remaining, turn_count, job_criteria); adaptive follow-up based on dimensions not yet adequately explored; on guard failure returns `blocked_redirect`
- [x] T062 [US3] Implement `/agents/interview/turn` endpoint in `agents/app/api/routers/interview.py` — receives full `InterviewState`; returns `{ai_response, updated_state, session_complete, dimensions_remaining, guardrail_triggered, blocked_redirect}` per contracts/agents.md
- [x] T063 [US3] Implement `InterviewService` in `backend/app/services/interview_service.py` — `handle_turn(session_id, candidate_input, mode)`: load Redis state → STT (if voice) → **upload raw audio bytes to `StorageService` and record `audio_blob_key` on the `InterviewMessage` before discarding audio bytes** → call agents `/interview/turn` → save updated state to Redis (TTL 25h) → persist message(s) with `audio_blob_key` → handle `guardrail_triggered` (store blocked turn with `is_blocked=true`, content_text=`[blocked]`, `audio_blob_key=None`) → TTS → return AI response; `handle_system_interrupt(session_id)`: set status `system_interrupted`, log to audit_log; `check_and_expire_sessions()`: sets `abandoned` status for sessions where `last_active_at` is older than 24h (C2)
- [x] T063a [US3] Initialize APScheduler in `backend/app/main.py` FastAPI `lifespan` handler — schedule `InterviewService.check_and_expire_sessions()` to run every hour; use `AsyncIOScheduler` from `apscheduler`; add `apscheduler` to `backend/pyproject.toml`; ensure scheduler shuts down cleanly on app stop (H3)
- [x] T064 [US3] Implement WebSocket endpoint in `backend/app/api/routers/interviews.py` — `WS /interviews/{token}/connect`; validates token (research §6); creates/loads session; sends `session_ready`; dispatches incoming messages to `InterviewService`; sends `turn_processing`, `ai_turn`, `turn_blocked`, `interview_complete`, `session_expired`, `service_error` per contracts/websocket.md; closes with correct WS close codes
- [x] T065 [US3] Implement `interview-ws.ts` WebSocket client in `frontend/src/services/interview-ws.ts` — typed message send/receive; MediaRecorder for audio capture; base64 encode audio for `audio_input` messages; expose `onAiTurn`, `onComplete`, `onError` callbacks
- [x] T066 [US3] Implement `InterviewRoomPage` in `frontend/src/pages/interview/InterviewRoomPage.tsx` — connects via `interview-ws.ts`; microphone record button; text input fallback toggle; plays AI audio responses (`<audio>` element); shows turn progress indicator; displays completion screen on `interview_complete`

**Checkpoint**: Full voice interview completes end-to-end. Interview tests T054/T055 pass. Harmful input results in `turn_blocked` and is not stored. System interruption sets status to `system_interrupted` and candidate can resume.

---

## Phase 6: User Story 4 — Recruiter Reviews Evaluations and Shortlists (Priority: P4)

**Goal**: Automated evaluation after interview completion, ranked shortlist, full evaluation detail with transcript and audio playback.

**Independent Test**: Complete one interview → `GET /jobs/{id}/evaluations` shows ranked candidate with score and recommendation → `GET /evaluations/{id}` shows dimension scores with evidence quotes and audio playback URLs. See [quickstart.md §Story 4](quickstart.md).

### Tests for User Story 4 (constitution-mandated — write FIRST, confirm FAILING before T073)

- [x] T067 [P] [US4] Write failing integration test: evaluation pipeline — trigger evaluation from completed interview → assert `overall_score`, `dimension_scores` with evidence_quotes, `consistency_flags`, `communication_quality`, and `confidence_flag` are persisted in `backend/tests/integration/test_evaluation.py` — mocks LLM calls; verifies PII-redacted output stored

### Implementation for User Story 4

- [x] T068 [P] [US4] Create Alembic migration for `evaluations` table with all columns from data-model.md; add `UNIQUE (application_id)` constraint; add `(company_id, overall_score DESC)` index; add RLS policy; **also add `summary TEXT NULLABLE` column** — required by FR-033 (feedback report must show strengths/areas-for-improvement summary); absent from original data-model.md but needed by T078 feedback router
- [x] T069 [P] [US4] Implement SQLAlchemy ORM model: `Evaluation` in `backend/app/models/evaluation.py`
- [x] T070 [US4] Implement `EvaluationRepository` in `backend/app/repositories/evaluation_repository.py` — async CRUD; `list_by_job_ranked(job_id)` orders by `overall_score DESC`; `get_by_feedback_token(token)` bypasses RLS (public endpoint)
- [x] T071 [US4] Implement `evaluation_graph` LangGraph `StateGraph` in `agents/app/graphs/evaluation_graph.py` — nodes: `score_dimensions`, `flag_consistency`, `score_communication`, `assess_confidence`, `generate_summary`; all LLM calls guarded; PII-redact all output including `evidence_quotes` and `consistency_flags` before returning; confidence_flag logic: set true when avg evidence_quotes per dimension < 1 OR overall turn depth < 0.3; **also create `agents/app/prompts/evaluation.py`** with `EVALUATION_SCORE_DIMENSIONS`, `EVALUATION_FLAG_CONSISTENCY`, `EVALUATION_SCORE_COMMUNICATION`, `EVALUATION_ASSESS_CONFIDENCE`, `EVALUATION_GENERATE_SUMMARY` prompt constants — import in `evaluation_graph.py` following the established `agents/app/prompts/` pattern
- [x] T072 [US4] Implement `/agents/evaluate` endpoint in `agents/app/api/routers/evaluation.py` — receives `{application_id, company_id, cv_text, job_criteria, transcript}`; returns full evaluation payload per contracts/agents.md
- [x] T077 [P] [US4→US5] Implement `EvaluationService.generate_feedback_token()` in `backend/app/services/evaluation_service.py` — UUID token, 30-day expiry; stored on `evaluations` row; must be available before T073 calls it *(moved from Phase 7 — T073 depends on this method)*
- [x] T073 [US4] Implement `EvaluationService.evaluate_from_session()` in `backend/app/services/evaluation_service.py` — triggered by `InterviewService` on `session_complete`; fetches transcript + CV text + job criteria; calls agents `/evaluate`; persists `Evaluation`; updates application status to `evaluated`; calls `generate_feedback_token()` (T077); calls `NotificationService.send_feedback_email`; logs to audit_log *(depends on T077)*
- [x] T074 [US4] Implement evaluations router in `backend/app/api/routers/evaluations.py` — `GET /jobs/{id}/evaluations` (ranked shortlist), `GET /evaluations/{id}` (full detail with transcript), `GET /evaluations/{id}/transcript/{turn_index}/audio` (streams audio: fetch `audio_blob_key` from `interview_messages` where `session_id = interview_sessions.id` joined via `applications`, and `turn_index = :turn_index`; stream bytes from `StorageService`); all recruiter-auth
- [x] T075 [US4] Implement `ShortlistPage` in `frontend/src/pages/evaluations/ShortlistPage.tsx` — ranked candidate cards with score, recommendation chip, confidence warning badge; links to evaluation detail
- [x] T076 [P] [US4] Implement `EvaluationDetailPage` in `frontend/src/pages/evaluations/EvaluationDetailPage.tsx` — dimension score breakdown with evidence quotes; consistency flags panel; communication quality metrics; full transcript with per-turn audio playback (`<audio>` elements)

**Checkpoint**: Evaluation completes ≤ 5 min after interview. Evaluation test T067 passes. Confidence flag is shown on the detail page when triggered. Audio playback works for candidate turns.

---

## Phase 7: User Story 5 — Candidate Receives a Feedback Report (Priority: P5)

**Goal**: Feedback email sent after evaluation; candidate accesses per-dimension report via secure token link with no account required.

**Independent Test**: Complete an evaluation → candidate receives email within 30 min → open feedback link → see dimension scores and summary → no hire/no-hire recommendation visible → expired token returns 410. See [quickstart.md §Story 5](quickstart.md).

- [x] T078 [US5] Implement feedback router in `backend/app/api/routers/feedback.py` — `GET /feedback/{token}` (public, no auth); calls `EvaluationRepository.get_by_feedback_token(token)` (bypasses RLS); returns `{job_title, overall_score, dimension_scores, summary}` — deliberately excludes `recommendation` (hire/no-hire is internal); returns 404 for unknown token, 410 for expired token (checks `feedback_token_expires_at`)
- [x] T079 [US5] Upgrade `send_feedback_email` in `backend/app/services/notification_service.py` to send an **HTML** email body — the plain-text method already exists; replace the body string with a formatted HTML template showing the job title, a link to the feedback report, and a brief message; dedup key already in place
- [x] T080 [US5] Implement `FeedbackReportPage` in `frontend/src/pages/feedback/FeedbackReportPage.tsx` — public route (no auth required); fetches `GET /feedback/{token}` from URL param; displays dimension score bars, strengths summary, areas-for-improvement summary; shows "link expired" state on 410

**Checkpoint**: Feedback email arrives within 30 min of interview completion. Feedback page loads without auth. Expired token shows clear expiry message. No hire/no-hire recommendation is visible to the candidate.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Deployment, observability, and validation of the full platform.

- [ ] T081 [P] Configure `infra/docker-compose.prod.yml` and GitHub Actions deploy workflow in `.github/workflows/deploy.yml` — Docker Hub image push on merge to `main`; Azure Container Apps rolling update via `az containerapp update`; `api` and `frontend` with external ingress, `agents` internal-only (research §9)
- [x] T082 [P] Write `infra/nginx.conf` — serves frontend SPA at `/`; proxies `/api` to the api service; handles SPA fallback routing (`try_files` to `index.html`)
- [x] T083a [P] Write tenant isolation integration test in `backend/tests/integration/test_tenant_isolation.py` — register two independent companies (A and B); assert Company B cannot list or fetch any of Company A's jobs, applications, evaluations, or users; covers SC-005 (100% data isolation); unauthenticated requests must return 401 (C1 remediation)
- [ ] T083 Run full end-to-end validation per `quickstart.md` — all 5 user stories + tenant isolation test + CI smoke test suite (`pytest tests/integration/ -v`); verify SC-002 SLA: submit 20 concurrent CVs and confirm all screening results appear within 2 minutes; verify SC-004 SLA: confirm evaluation reports appear within 5 minutes for each completed interview
- [ ] T084 [P] Performance audit — profile p95 API latency for synchronous endpoints under simulated load (locust or k6); address TODO(PERFORMANCE_BASELINE) in constitution; verify ≤ 300 ms p95; separately measure async pipeline timings (screening, evaluation) to confirm SC-002 and SC-004 SLAs hold at expected load (M1)
- [ ] T084b [P] RAGAS evaluation suite — install `ragas` in `backend/` dev dependencies; **first create golden-set fixtures**: 20 synthetic CV samples in `backend/tests/ragas/fixtures/cvs/` and 5 interview transcript samples in `backend/tests/ragas/fixtures/transcripts/` (curate manually — these are the ground-truth datasets RAGAS scores against); then write `backend/tests/ragas/test_screening_rag.py` and `backend/tests/ragas/test_evaluation_rag.py`; assert **faithfulness ≥ 0.85** (LLM rationale/evidence grounded in retrieved context, no hallucinated skills or quotes) and **context precision ≥ 0.80** (hybrid search top-k chunks are relevant to job criteria); log per-run scores to `audit_log` under event type `pipeline.quality.ragas`; fail CI if either threshold is breached
- [ ] T085 [P] Accessibility audit — run axe-core against all frontend pages; fix any WCAG 2.1 AA violations (Principle I)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Requires Phase 1 — **blocks all user story phases**
- **Phase 3–7 (User Stories)**: All require Phase 2 completion; can proceed in priority order (P1 → P2 → P3 → P4 → P5) or in parallel across developers
- **Phase 8 (Polish)**: Requires all desired user story phases complete

### User Story Dependencies

| Story | Depends On | Notes |
|---|---|---|
| US1 (P1) | Phase 2 only | No story dependencies |
| US2 (P2) | Phase 2 + US1 active | Needs active job to apply to; screening calls agent service configured in US1 |
| US3 (P3) | US2 qualified | Needs a qualified application to invite for interview |
| US4 (P4) | US3 completed | Needs a completed interview transcript to evaluate |
| US5 (P5) | US4 completed | Needs evaluation with feedback_token |

### Within Each User Story

1. Constitution-mandated tests MUST be written first and confirmed failing
2. Alembic migration before ORM models
3. ORM models before repositories
4. Repositories before services
5. Services before routers
6. Routers before frontend pages

### Parallel Opportunities

- **Phase 1**: T002, T003, T004 (different project dirs); T006, T007 run in parallel
- **Phase 2**: T008/T009 in parallel; T012/T013 in parallel; T014/T015 in parallel; T018/T019 in parallel
- **US1**: T021/T022 tests in parallel; T023/T024/T029 in parallel (migrations + models); T035/T036/T037 frontend in parallel
- **US2**: T038/T039 tests in parallel; T040/T041/T042 migrations + models in parallel; T052/T053 frontend in parallel
- **US3**: T054/T055 tests in parallel; T056/T057 in parallel; T059/T060 (STT/TTS) in parallel
- **US4**: T068/T069 migration + model in parallel; T075/T076 frontend in parallel
- **US5**: T077/T079 (token generation + email template) in parallel

---

## Parallel Example: User Story 1

```bash
# After Phase 2 completes — launch in parallel:
Task T021: "Write failing auth test: registration"          # backend/tests/integration/test_auth.py
Task T022: "Write failing auth test: token lifecycle"       # backend/tests/integration/test_auth.py
Task T023: "Alembic migration: jobs, job_criteria, setup_conversations"
Task T024: "ORM models: Company, User"                      # backend/app/models/
Task T029: "ORM models: Job, JobCriteria, SetupConversation" # backend/app/models/

# After T024 + T025:
Task T026: "Implement AuthService"                          # depends on T024, T025
Task T027: "Implement auth router"                          # depends on T026

# After T029 + T030:
Task T031: "Implement job_setup_graph"                      # agents/app/graphs/
Task T033: "Implement JobService"                           # depends on T030, T031, T032
```

---

## Parallel Example: User Story 3

```bash
# Launch in parallel after US2 complete:
Task T054: "Write failing WS interview turn test"
Task T055: "Write failing session resume/expiry test"
Task T056: "Alembic migration: interview_sessions, interview_messages"
Task T057: "ORM models: InterviewSession, InterviewMessage"

# After T057:
Task T059: "Implement SttService"                           # independent
Task T060: "Implement TtsService"                           # independent
Task T061: "Implement interview_graph"                      # agents service, independent

# After T058 + T059 + T060 + T062:
Task T063: "Implement InterviewService"                     # orchestrates all above
Task T064: "Implement WebSocket endpoint"                   # depends on T063
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL)
3. Write and confirm-failing T021/T022
4. Complete Phase 3: User Story 1
5. **STOP and VALIDATE**: auth tests pass, job is activatable, tenant isolation confirmed
6. Deploy and demo

### Incremental Delivery

1. **Setup + Foundational** → infrastructure ready
2. **+US1** → recruiters can create and configure jobs (MVP!)
3. **+US2** → candidates can apply; recruiters see screening results
4. **+US3** → voice interviews run end-to-end
5. **+US4** → recruiters can make shortlist decisions
6. **+US5** → candidates receive feedback; full loop closed

### Parallel Team Strategy (3 developers after Phase 2)

| Developer | Tracks |
|---|---|
| Dev A | US1 backend (auth + job setup + agents job_setup_graph) |
| Dev B | US1 frontend (login, register, job setup UI) |
| Dev C | Phase 2 completion (storage, guardrails, notifications) |
| → merge US1 → | |
| Dev A | US2 backend (screening pipeline) |
| Dev B | US2 frontend (application form, list) |
| Dev C | US3 backend (interview WebSocket, STT/TTS) |

---

## Notes

- `[P]` tasks operate on different files with no shared in-progress dependencies
- `[Story]` label maps each task to a user story for traceability
- Constitution Principle VIII makes test tasks T021/T022/T038/T039/T054/T055/T067 **non-negotiable** — no merge to main without them
- Each phase checkpoint is a valid delivery point; stop and validate before proceeding
- Commit after each completed task or logical group
- Avoid cross-story service dependencies that break independent testability


---

---

# V2 — Post-MVP Features

> V2 tasks each get their own feature branch created with `/speckit-git-feature`.
> Each story below maps to a branch: `00N-story-slug`.
> Branch strategy: one branch per V2 story → own `specs/00N-story-slug/` dir → own `plan.md` + `tasks.md` generated by running `/speckit-plan` and `/speckit-tasks` on that branch.

**Task IDs continue from T086 to avoid collision with MVP tasks.**

---

## Phase 9: V2 Story 1 — Additional CV File Formats (V2-1)

**Branch**: `010-cv-file-formats`

**Goal**: Accept DOCX and image files (JPG, PNG) in addition to PDF. Spec defers this to V2.

- [ ] T086 [P] [V2-1] Add DOCX extraction to `OcrService` in `backend/app/services/ocr_service.py` — use `python-docx` to extract paragraphs and tables; apply same quality heuristic (word_count < 50 → Azure Document Intelligence fallback)
- [ ] T087 [P] [V2-1] Add image CV extraction to `OcrService` in `backend/app/services/ocr_service.py` — accept JPG/PNG; route directly to Azure Document Intelligence `prebuilt-document`; skip PyMuPDF path entirely
- [ ] T088 [V2-1] Update file validation in `backend/app/api/routers/applications.py` — accept `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `image/jpeg`, `image/png`; keep 10 MB cap; update MIME type error messages
- [ ] T089 [V2-1] Update `JobApplicationPage` in `frontend/src/pages/applications/JobApplicationPage.tsx` — file input `accept` attribute updated to include DOCX and image types; hint text lists all supported formats

**Checkpoint**: DOCX and image CVs produce screening results at the same quality as the PDF path. Unsupported formats still return 422.

---

## Phase 10: V2 Story 2 — Analytics Dashboard (V2-2)

**Branch**: `015-analytics-dashboard`

**Goal**: Recruiters see aggregated hiring funnel metrics per job and company-wide: applications received, qualification rate, interview completion rate, average evaluation score, p50/p95 time-to-screen and time-to-evaluate.

- [ ] T090 [P] [V2-2] Implement `AnalyticsService` in `backend/app/services/analytics_service.py` — `get_job_funnel(job_id)`: queries `applications` and `evaluations` grouped by status; computes counts, pass/fail rates, average score, p50/p95 timings using timestamps already on each record
- [ ] T091 [V2-2] Add per-job analytics endpoint `GET /jobs/{id}/analytics` (recruiter auth) in `backend/app/api/routers/jobs.py` — returns funnel metrics JSON
- [ ] T092 [P] [V2-2] Add company-wide analytics endpoint `GET /analytics/overview` (recruiter auth) in `backend/app/api/routers/analytics.py` — aggregates across all jobs: total applications this month, overall screening pass rate, overall avg evaluation score
- [ ] T093 [P] [V2-2] Implement `JobAnalyticsPage` in `frontend/src/pages/jobs/JobAnalyticsPage.tsx` — funnel bar chart (Recharts), score distribution histogram, avg time-to-screen and time-to-evaluate stat cards; linked from job detail page
- [ ] T094 [V2-2] Implement `OverviewDashboardPage` in `frontend/src/pages/OverviewDashboardPage.tsx` — company-wide KPI cards at top; job list below; replaces `JobListPage` as the default landing page after login

**Checkpoint**: For a job with 20+ applications, analytics page shows correct funnel counts and rates. Overview page loads with company-wide aggregates.

---

## Phase 11: V2 Story 3 — Real-Time Streaming Voice Interview (V2-3)

**Branch**: `017-video-interview`

**Goal**: Replace the turn-based voice model (MVP) with real-time streaming voice — candidate speaks continuously, VAD detects end-of-speech, STT transcribes incrementally, LLM responds, TTS streams audio back chunk-by-chunk. Eliminates the 10-second wait and makes the conversation feel natural.

- [ ] T094a [V2-3] Add `silero-vad`, `onnxruntime` to `backend/pyproject.toml` and rebuild the backend Docker image — these are required by `VadService` (T097); verify ONNX runtime loads the silero model at startup without errors (H4)
- [ ] T095 [P] [V2-3] Add `streaming_mode` boolean column (default false) to `interview_sessions` table — Alembic migration in `backend/alembic/versions/`; existing turn-based sessions unaffected
- [ ] T096 [P] [V2-3] Extend WebSocket protocol in `contracts/websocket.md` — add `audio_chunk` client→server message type (base64-encoded PCM 16-bit 16kHz frames, ~100ms each); add `ai_audio_chunk` server→client message type (base64-encoded MP3 chunk for streaming playback); add `vad_end_of_turn` server→client message (signals end-of-speech detected, AI is generating)
- [ ] T097 [V2-3] Implement `VadService` in `backend/app/services/vad_service.py` — wraps `silero-vad` (ONNX, runs in-process via `onnxruntime`); `detect_end_of_turn(audio_buffer)` returns True after ≥ 800ms of silence following speech; segments continuous audio into complete candidate utterances without requiring a button press
- [ ] T098 [V2-3] Add `transcribe_stream(audio_chunks_iter)` to `SttService` in `backend/app/services/stt_service.py` — buffers incoming PCM chunks; on VAD end-of-turn fires full buffer to OpenAI Whisper API; yields transcript text; handles mid-stream silence and noise gracefully
- [ ] T099 [V2-3] Add `synthesize_stream(text)` to `TtsService` in `backend/app/services/tts_service.py` — calls OpenAI TTS with `stream=True`; yields MP3 byte chunks as they arrive so the frontend can start playback before synthesis finishes; falls back to Azure AI Speech if OpenAI TTS streaming fails
- [ ] T100 [V2-3] Add `handle_streaming_turn(session_id, ws)` async generator to `InterviewService` in `backend/app/services/interview_service.py` — pipes `audio_chunk` WS messages → `VadService` → `SttService.transcribe_stream` → guardrail check → agents `/interview/turn` → `TtsService.synthesize_stream` → `ai_audio_chunk` WS messages; sends `vad_end_of_turn` when VAD fires; falls back to turn-based path when `streaming_mode=False`
- [ ] T101 [V2-3] Update WebSocket endpoint in `backend/app/api/routers/interviews.py` — on connect, set `streaming_mode` from job config; route incoming `audio_chunk` messages to `handle_streaming_turn`; forward `ai_audio_chunk` frames immediately as they are yielded
- [ ] T102 [V2-3] Refactor `InterviewRoomPage` in `frontend/src/pages/interview/InterviewRoomPage.tsx` — replace record-then-send button with continuous microphone capture via `AudioWorklet` (128-frame PCM chunks at 16kHz); send frames as `audio_chunk` WS messages; enqueue received `ai_audio_chunk` frames into a `MediaSource` buffer for gapless streaming playback; show live waveform visualizer during candidate speech; show spinner on `vad_end_of_turn` while AI generates
- [ ] T103 [P] [V2-3] Write integration tests for streaming mode in `backend/tests/integration/test_interview_streaming.py` — simulate chunked PCM audio input over WS; assert `vad_end_of_turn` fires after silence threshold; assert `ai_audio_chunk` frames received before full TTS completes; assert complete transcript stored after streaming turn

**Checkpoint**: Candidate speaks without pressing any button; AI responds within 2 seconds of end-of-speech detection; audio starts playing before full synthesis completes. Full transcript stored identically to turn-based mode.

---

## V2 Branch Strategy

Use `/speckit-git-feature` to create each branch, then generate a dedicated plan and task list on that branch:

```bash
# Example: create the file formats branch
/speckit-git-feature   # follow prompts → enter "010-cv-file-formats"

# Then on that branch, generate a scoped plan and tasks:
/speckit-plan          # generates specs/010-cv-file-formats/plan.md
/speckit-tasks         # generates specs/010-cv-file-formats/tasks.md
```

Each V2 branch has its own `specs/00N-story-slug/` directory with an independent plan, data-model delta, contracts delta, and task list. All V2 branches cut from `main` after the MVP is merged — not from each other.

## V2 Dependency Map

| V2 Story | Branch | Depends On | Notes |
|---|---|---|---|
| V2-1 File formats | `010-cv-file-formats` | MVP complete | No V2 dependencies |
| V2-2 Analytics | `015-analytics-dashboard` | MVP complete | No V2 dependencies |
| V2-3 Streaming voice | `017-video-interview` | MVP complete | Adds `silero-vad` + `onnxruntime` to backend deps; replaces turn-based WS protocol |

All three V2 stories are independently startable once MVP is merged to `main`. None block each other.
