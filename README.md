# HireIQ — AI-Powered Hiring Platform

HireIQ is a multi-tenant, AI-driven hiring platform that runs the whole pipeline from
posting a job to giving a candidate their feedback report. Recruiters set up a job with an
AI assistant, candidates' CVs are screened automatically, applicants take a **real-time
voice interview with an AI interviewer (Sila)**, the platform produces an LLM-driven
evaluation, and candidates receive a structured feedback report. Companies can also source
open-to-work candidates directly inside the app.

🔗 **Live (hosted on Azure Container Apps):**
https://hireiq-frontend.redbush-801cefdb.westus2.azurecontainerapps.io/

📹 **Demos** (in [`demo/`](demo/)):
- [`demo/demo_platform.mp4`](demo/demo_platform.mp4) — full platform walkthrough
- [`demo/demo_interview.mp4`](demo/demo_interview.mp4) — the AI voice interview

---

## What it does

HireIQ delivers an end-to-end hiring funnel, with every stage tenant-isolated at the
database level (PostgreSQL Row-Level Security):

1. **AI-guided job setup** — a recruiter describes a role and an AI assistant helps shape
   the job, requirements, and screening criteria.
2. **CV screening** — uploaded CVs (PDF, DOCX, and JPG/PNG/scanned via OCR) are parsed and
   ranked using hybrid vector search (pgvector) against the job criteria.
3. **Real-time voice interview** — candidates have a natural, streaming voice conversation
   with **Sila**, the AI interviewer, over a WebSocket. Speech is detected client-side
   (silero-VAD), recognized and synthesized via Azure Speech streaming STT/TTS, so playback
   starts before synthesis finishes. A turn-based text path is the fallback.
4. **LLM-driven evaluation** — interview transcripts are evaluated, with guardrails and PII
   redaction applied before anything is stored or surfaced.
5. **Candidate feedback report** — each candidate receives a structured feedback report.
6. **Candidate accounts & in-app sourcing** — candidates register, store a CV, browse jobs
   and one-click apply; companies can enable sourcing on a job and invite strong, open-to-work
   matches (company-blind so the candidate decides).
7. **Analytics dashboard** — aggregated hiring-funnel metrics per job and company-wide.

### Architecture

A multi-service monorepo deployed as separate containers:

| Service | Stack | Role |
|---|---|---|
| `backend/` | FastAPI (async), SQLAlchemy 2.0 + asyncpg, Alembic | Public API: auth, jobs, applications, interviews (WebSocket), evaluations, feedback. Owns session state in Redis. |
| `agents/`  | FastAPI, LangGraph, langchain-openai | Stateless AI agent service: job setup, CV screening, interview turns, evaluation — with a guardrail registry + PII redactor. **No database access.** |
| `frontend/`| React 18 + Vite + TypeScript + Tailwind | Single-page app (recruiter + candidate experiences), WCAG 2.1 AA. |

**Data & infra:** PostgreSQL 16 + pgvector (RLS-enforced primary store), Redis 7 (session
state, rate limiting, email dedup), Azure Blob Storage / local filesystem (CV files &
interview audio), HashiCorp Vault (local dev) / Azure Key Vault (prod) for secrets.

**External services:** OpenAI (LLM), Azure Speech (voice STT/TTS),
Azure Document Intelligence (scanned-CV OCR), Resend (transactional email), Langfuse (LLM
tracing).

---

## Run it locally

Everything runs with Docker Compose — 8 services (postgres, redis, vault, vault-init,
migrate, api, agents, frontend) wired together.

### Prerequisites

- Docker & Docker Compose
- An OpenAI API key (the AI pipeline stages need it). Azure Speech, OCR, email, and tracing
  keys are optional — leave them blank to disable those features.

### Steps

```bash
# 1. Configure local secrets
cp infra/.env.example infra/.env
#    then edit infra/.env and set at least:
#      OPENAI_API_KEY=sk-...
#      JWT_SECRET=<a long random string>
#    (Azure Speech / OCR / email / Langfuse keys are optional)

# 2. Bring up the whole stack
cd infra
docker compose up --build
```

On startup the stack seeds Vault from `infra/.env`, runs Alembic migrations to head, then
starts the API, agents, and frontend services.

Once it's up:

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API (FastAPI) | http://localhost:8000 |
| Agents service | http://localhost:8001 |
| Postgres | localhost:5432 (`hireiq` / `hireiq_dev`) |
| Redis | localhost:6379 |
| Vault (dev) | http://localhost:8200 (token `hireiq-dev-token`) |

Both Python services expose `/health`.

### Frontend dev (hot reload, optional)

To work on the UI against the running API without rebuilding the container:

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
# Backend / agents (pytest + pytest-asyncio)
cd backend && pytest
cd agents  && pytest

# Frontend (Vitest, incl. a11y checks)
cd frontend && npm run test:a11y
```

---

## Project layout

```text
backend/    FastAPI public API service (routers, services, repositories, models, alembic)
agents/     LangGraph AI agent service (graphs, nodes, guardrails) — no DB access
frontend/   React + Vite + TypeScript SPA
infra/      docker-compose (dev + prod), Vault seeding, env example
specs/      Spec-driven feature plans (job platform, voice interview, sourcing, analytics…)
demo/       Demo recordings of the platform and the interview
```

For deeper design context, see the feature plans under `specs/` — the MVP baseline is
[`specs/001-ai-hiring-platform/plan.md`](specs/001-ai-hiring-platform/plan.md) and the
streaming voice interview is [`specs/017-video-interview/plan.md`](specs/017-video-interview/plan.md).
