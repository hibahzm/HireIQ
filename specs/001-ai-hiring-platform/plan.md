# Implementation Plan: HireIQ — AI-Powered Hiring Platform (MVP)

**Branch**: `001-ai-hiring-platform` | **Date**: 2026-06-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-ai-hiring-platform/spec.md`

---

## Summary

HireIQ is a multi-tenant AI-powered hiring platform built with FastAPI async, LangGraph agents, PostgreSQL 16 with pgvector and RLS, and a React/Vite TypeScript frontend. The MVP delivers five pipeline stages in priority order: AI-guided job setup → CV screening with hybrid vector search → voice interview over WebSocket → LLM-driven evaluation with PII redaction → candidate feedback report. The api service and agents service are decoupled — the agents service is stateless per request; the api service owns session persistence in Redis. All data is tenant-isolated at the database level via Row-Level Security.

---

## Technical Context

**Language/Version**: Python 3.12, Node 20 (frontend)

**Primary Dependencies**:
- **api service**: `fastapi 0.115`, `sqlalchemy[asyncio] 2.0`, `asyncpg`, `alembic`, `python-jose[cryptography]`, `bcrypt`, `httpx`, `redis[asyncio]`, `azure-storage-blob`, `PyMuPDF`, `azure-ai-formrecognizer`, `openai`, `azure-identity`, `hvac`, `structlog`, `pydantic-settings`, `pgvector`, `resend` (transactional email)
- **agents service**: `fastapi 0.115`, `langgraph`, `langchain-openai`, `openai`, `structlog`
- **frontend**: `react 18`, `vite 5`, `typescript 5`, `tailwindcss 3`

**Storage**:
- PostgreSQL 16 + pgvector extension (primary store, RLS enforced)
- Redis 7 (interview session state, rate limiting, email dedup, refresh token invalidation)
- Azure Blob Storage / local filesystem fallback (CV files, interview audio recordings)

**Email**:
- Provider: [Resend](https://resend.com) (MVP — simple HTTP API, free tier, no SMTP config needed)
- Config vars: `EMAIL_API_KEY`, `EMAIL_FROM` (e.g., `noreply@hireiq.io`) in `config.py`
- Transactional only: confirmation, invitation, feedback emails (FR-012, FR-015, FR-031)
- Dev fallback: log email content to stdout when `EMAIL_BACKEND=console`

**Testing**: `pytest 8`, `httpx.AsyncClient`, `pytest-asyncio`; LLM calls mocked via `unittest.mock`

**Target Platform**: Docker Compose (local dev, 6 services), Azure Container Apps (production)

**Project Type**: Multi-service web application (2 Python services + 1 React SPA + PostgreSQL + Redis + Vault)

**Performance Goals**:
- API responses: p95 ≤ 300 ms (constitution standard; TODO(PERFORMANCE_BASELINE) still open for load profile)
- CV screening results available ≤ 2 min for 95% of submissions (SC-002)
- Evaluation reports available ≤ 5 min post interview (SC-004)
- Voice turn response delivered ≤ 10 s end-to-end (acceptance scenario for US-3)

**Constraints**:
- All Python functions `async` — synchronous DB or HTTP calls are a defect (Principle II)
- RLS `SET LOCAL app.current_company_id` required before every DB query (Principle VI)
- Guardrail registry wraps every LLM call; PII redaction before storage (Principle V)
- WCAG 2.1 AA for all frontend components (Principle I)
- No secrets in code; all secrets via `config.py` backed by Vault / Azure Key Vault (Principle IV)

**Scale/Scope**: MVP — tens of companies, hundreds of applications per job, interview sessions ≤ 20 turns / 30 min

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-evaluated after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. User-First Design | ✅ PASS | 5 user stories in spec.md covering all pipeline stages; WCAG 2.1 AA required in design |
| II. Async-First Python | ✅ PASS | asyncpg + SQLAlchemy 2.0 async; httpx.AsyncClient; no sync calls anywhere |
| III. Clean Architecture | ✅ PASS | Repository layer for all DB access; thin route handlers; FastAPI `Depends()` wiring throughout |
| IV. Secrets & Credentials Hygiene | ✅ PASS | Vault (local dev) + Azure Key Vault (prod) via `config.py`; `.env*` excluded from git |
| V. AI Agent Safety & PII Protection | ✅ PASS | Guardrail registry + PIIRedactor designed (research §7); all agent outputs pass through redaction before storage |
| VI. Multi-Tenant Data Isolation | ✅ PASS | `SET LOCAL` RLS pattern per research §1; every tenant-scoped table has `company_id`; migration user uses BYPASSRLS |
| VII. Observability & Reliability | ✅ PASS | `audit_log` table; `/health` on both services; structlog with correlation ID on all request paths |
| VIII. Test Coverage | ✅ PASS | pytest + pytest-asyncio; TDD required for auth, CV screening pipeline, voice interview turns, evaluation pipeline |

**Post-Phase 1 re-check**: ✅ No new violations. All entities have `company_id`. Agent contract enforces guardrail calls. Contracts expose `/health`. RLS migration pattern accounts for cv_chunks and job_chunks.

---

## Project Structure

### Documentation (this feature)

```text
specs/001-ai-hiring-platform/
├── plan.md              # This file
├── research.md          # Phase 0 — resolved decisions
├── data-model.md        # Phase 1 — entities, fields, relationships, state machines
├── quickstart.md        # Phase 1 — end-to-end validation guide
├── contracts/
│   ├── api.md           # REST API contract (api service, public)
│   ├── websocket.md     # WebSocket protocol (voice interview)
│   └── agents.md        # Internal agents service API (api → agents)
└── tasks.md             # Phase 2 output — generated by /speckit-tasks (NOT this command)
```

### Source Code (repository root)

```text
backend/                          # FastAPI api service (public-facing)
├── app/
│   ├── api/
│   │   ├── routers/
│   │   │   ├── auth.py           # /auth/*
│   │   │   ├── companies.py      # /companies/*
│   │   │   ├── jobs.py           # /jobs/*
│   │   │   ├── applications.py   # /jobs/{id}/applications, /applications/{id}
│   │   │   ├── interviews.py     # WebSocket /interviews/{token}/connect
│   │   │   ├── evaluations.py    # /evaluations/*, /jobs/{id}/evaluations
│   │   │   └── feedback.py       # /feedback/{token}
│   │   └── deps.py               # FastAPI Depends() — DB session (with RLS), current user
│   ├── models/                   # SQLAlchemy ORM models (one file per entity)
│   ├── repositories/             # Async repository classes (no raw queries in routes/services)
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── job_service.py
│   │   ├── screening_service.py  # Calls agents service; persists results
│   │   ├── interview_service.py  # WebSocket orchestration; Redis state; audit logging
│   │   ├── evaluation_service.py
│   │   ├── notification_service.py  # Transactional email dispatch
│   │   └── storage_service.py    # Azure Blob / local filesystem
│   ├── schemas/                  # Pydantic request/response models
│   ├── config.py                 # Settings class (Vault/Azure Key Vault backed)
│   └── main.py
├── alembic/
│   ├── env.py
│   └── versions/                 # Migration files
└── tests/
    ├── unit/
    └── integration/

agents/                           # LangGraph agents service (internal, not publicly reachable)
├── app/
│   ├── api/
│   │   └── routers/
│   │       ├── job_setup.py      # POST /agents/job-setup/turn
│   │       ├── interview.py      # POST /agents/interview/turn
│   │       ├── screening.py      # POST /agents/cv-screen
│   │       └── evaluation.py     # POST /agents/evaluate
│   ├── graphs/                   # LangGraph StateGraph definitions
│   │   ├── job_setup_graph.py
│   │   ├── interview_graph.py
│   │   ├── screening_graph.py
│   │   └── evaluation_graph.py
│   ├── nodes/                    # Graph node functions
│   ├── guardrails/
│   │   ├── registry.py           # GuardRegistry — wraps all LLM calls
│   │   └── pii_redactor.py       # PIIRedactor.redact()
│   ├── config.py
│   └── main.py
└── tests/

frontend/                         # React + Vite + TypeScript SPA
├── src/
│   ├── components/               # Reusable UI components
│   ├── pages/
│   │   ├── auth/                 # Login, register
│   │   ├── jobs/                 # Job list, job detail, job setup
│   │   ├── applications/         # Application list, detail
│   │   ├── interview/            # Interview room (WebSocket + audio)
│   │   ├── evaluations/          # Shortlist, evaluation detail
│   │   └── feedback/             # Candidate feedback report
│   ├── services/
│   │   ├── api.ts                # Typed API client (axios or fetch)
│   │   └── interview-ws.ts       # WebSocket client for interview
│   └── hooks/
└── tests/

infra/
├── docker-compose.yml            # Local dev (api, agents, frontend, postgres, redis, vault)
├── nginx.conf                    # Frontend serving + proxy config
└── .github/
    └── workflows/
        ├── ci.yml                # Lint + test on push
        └── deploy.yml            # Docker Hub push + ACA deploy on main merge
```

**Structure Decision**: Multi-service monorepo. `backend/` and `agents/` are separate Python projects with separate `pyproject.toml` files — deployed as separate containers. `frontend/` is a Vite SPA. This separation enforces the constitution constraint that the agents service has no database access.

---

## Complexity Tracking

No constitution violations introduced. No justification table needed.
