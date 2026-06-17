# Implementation Plan: Candidate Accounts & In-App Talent Sourcing

**Branch**: `018-candidate-accounts-sourcing` | **Date**: 2026-06-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/018-candidate-accounts-sourcing/spec.md`

---

## Summary

Introduce a **second authenticated principal** — the job-seeking *candidate* — to a platform
that is currently company-only. At register/login the user picks **company** (hiring) or
**candidate** (job-seeking). Candidate accounts live on the existing **global, no-RLS
`candidates` table** (extended with auth + `open_to_work`), authenticated by a candidate JWT
that carries **no `company_id`** (`typ: "candidate"`). Each candidate stores **one CV** in a new
global `candidate_cvs` table, embedded as a **single whole-CV pgvector row** (not chunked) plus a
structured `skills` JSONB and a full-text `tsv`. Candidates **browse open jobs and one-click
apply**; applying **snapshots** the stored CV onto the `application`, so the existing CV Screening
Agent pipeline runs unchanged. A `(job_id, candidate)` + email dedup blocks double-applying
across the account and public-external routes.

Phase 2 adds company-side **in-app sourcing**: a per-job `sourcing_enabled` flag, and a **hybrid,
experience-aware search** — whole-CV pgvector cosine recall + Postgres full-text keyword +
structured `{skill, years, years_basis}` matching against `job_criteria` — so "Node.js 3y"
outranks "2y". Only `open_to_work` candidates are eligible; contact details are withheld until a
candidate accepts an invitation, which creates a deduplicated application.

This reuses `OcrService`, `EmbeddingService`, `AuthService`, the apply/dedup pipeline, the invite
+ `NotificationService` flow, and the `public_read_active_jobs` policy.

---

## Technical Context

**Language/Version**: Python 3.12 (backend), Node 20 / TypeScript 5 (frontend) — unchanged.

**Primary Dependencies**: FastAPI, SQLAlchemy async, Alembic, pgvector, Redis, `bcrypt`/`jose`
(reuse `AuthService`), OpenAI embeddings (`text-embedding-3-small`, reuse `EmbeddingService`),
existing `OcrService`. Phase 2 adds an LLM skill/years extractor (reuse the agents/LLM stack).
**No new third-party services.**

**Storage**: PostgreSQL with RLS. **Migrations**: (Phase 1) extend `candidates` with auth +
`open_to_work`; new global `candidate_cvs` (single `vector(1536)` embedding, `skills` JSONB, `tsv`,
ivfflat + GIN indexes). (Phase 2) `jobs.sourcing_enabled BOOLEAN`. `candidate_cvs`/`candidates`
stay **global (no RLS)**; cross-company reads are gated in the app layer to `open_to_work = true`.

**Testing**: `pytest` + `pytest-asyncio` (backend), Vitest (frontend). Auth, dedup, and ranking
are **Constitution-VIII TDD-mandated** domains (security + correctness) — failing-first, gating.

**Target Platform**: Docker Compose (dev) / Azure Container Apps (prod) — unchanged.

**Project Type**: Multi-service web app (backend + agents + frontend) — unchanged.

**Constraints**: candidate data is intentionally cross-company for sourcing, so multi-tenant
isolation must be enforced at the app layer (only `open_to_work` candidates visible; contact
details hidden pre-acceptance; no candidate may read company hiring data). Whole-CV embedding can
exceed the 8191-token model limit → keep most-recent experience + audit-log truncation. The
skill/years extractor must never fabricate years (`years_basis ∈ {stated, inferred_from_dates,
unknown}`).

**Scale/Scope**: One new principal type + auth path, one new candidate API surface, one new
global CV table, a hybrid sourcing search service, and a candidate-facing frontend portal.

## Constitution Check

*GATE: Must pass before Phase 0. Re-check after design.*

| Principle | Status | Notes |
|---|---|---|
| I. User-First Design | ✅ PASS | Candidate self-service (register, CV, browse, one-click apply); consent-based sourcing; clear duplicate/closed-job messaging; WCAG-AA forms reused. |
| II. Async-First Python | ✅ PASS | All new endpoints/services are async; embedding + LLM extraction use existing async clients; screening stays fire-and-forget with its own session. |
| III. Clean Architecture | ✅ PASS | New `candidates` router is a thin transport adapter; auth logic in `AuthService`; CV/sourcing logic in services; persistence in repositories. |
| IV. Secrets & Credentials Hygiene | ✅ PASS | Reuses `config.py`/Vault for JWT + OpenAI keys; bcrypt password hashing reused; no new secret source. |
| V. AI Agent Safety & PII | ⚠️ PASS w/ care | Skill/years extractor must not fabricate years; candidate PII (contact details) withheld until invitation accepted; CV text handled like existing application CVs. |
| VI. Multi-Tenant Isolation | ⚠️ PASS w/ care | `candidates`/`candidate_cvs` are global by design; **app-layer guardrails** restrict company reads to `open_to_work` candidates and hide contact info; candidate tokens (no `company_id`) cannot touch company RLS data. Gating tests required. |
| VII. Observability & Reliability | ✅ PASS | Reuse `audit_log` for candidate register/login, CV upload (+ truncation event), apply, invite/accept. `/health` unaffected. |
| VIII. Test Coverage (NON-NEGOTIABLE) | ✅ PASS (gating) | Failing-first tests for token-type isolation, apply dedup (account + external), CV single-embedding, ranking (3y > 2y), open_to_work exclusion, contact-hiding. |

**Post-design re-check**: ✅ No new violations. Two "with care" items (V, VI) are addressed by
app-layer access guards + gating tests; no new agent bypass, secret source, or tenant-data path
for company users.

## Project Structure

### Documentation (this feature)

```text
specs/018-candidate-accounts-sourcing/
├── plan.md            # This file
├── spec.md            # Feature spec (both candidate + company sides)
├── data-model.md      # Entities + migrations
├── checklists/
│   └── requirements.md
└── tasks.md           # (optional) generate via /speckit-tasks; tracked here via the todo list
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/
│   │   ├── candidate.py            # MODIFY — auth columns + open_to_work
│   │   ├── candidate_cv.py         # NEW — single whole-CV row (embedding, skills, tsv)
│   │   └── job.py                  # MODIFY (Phase 2) — sourcing_enabled
│   ├── repositories/
│   │   ├── candidate_repository.py # MODIFY — auth lookups, profile updates
│   │   └── candidate_cv_repository.py  # NEW — upsert/get CV, sourcing query
│   ├── services/
│   │   ├── auth_service.py         # MODIFY — candidate token + register/authenticate
│   │   ├── embedding_service.py    # MODIFY — whole-CV embed + token-cap handling
│   │   ├── cv_skill_extractor.py   # NEW (Phase 2) — {skill, years, years_basis}
│   │   └── sourcing_service.py     # NEW (Phase 2) — hybrid experience-aware ranking
│   ├── api/routers/
│   │   ├── auth.py                 # MODIFY — account_type on register/login
│   │   ├── candidates.py           # NEW — CV, profile, browse, one-click apply, invitations
│   │   ├── jobs.py                 # MODIFY (Phase 2) — sourcing_enabled
│   │   └── applications.py         # MODIFY (Phase 2) — sourcing search + invite-accept
│   └── api/deps.py                 # MODIFY — get_current_candidate dependency
├── alembic/versions/
│   ├── 0020_candidate_accounts.py  # NEW — candidates auth + candidate_cvs
│   └── 0021_job_sourcing.py        # NEW (Phase 2) — jobs.sourcing_enabled
└── tests/                          # NEW — auth isolation, dedup, embedding, ranking

frontend/src/
├── pages/auth/                     # MODIFY — company/candidate toggle
├── context|hooks/                  # MODIFY — candidate auth state + guard
├── services/api.ts                 # MODIFY — candidate token handling
├── pages/candidate/                # NEW — Dashboard, CV, BrowseJobs, MyApplications, Invitations
└── App.tsx                         # MODIFY — candidate routes
```

**Structure Decision**: Keep candidate identity on the existing **global `candidates` table**
(matches the "candidates — global, no RLS" design) rather than the company-locked `users` table.
Candidate auth is a parallel path through `AuthService`; the candidate API is a new router; the
apply pipeline + dedup + screening are reused unchanged. Sourcing is an additive service that
reads the global CV index under app-layer consent/privacy guards.

## Phases

- **Phase 1 (P1, shippable alone)**: migration (candidates auth + `candidate_cvs`), candidate
  auth path, candidate CV/profile/browse/one-click-apply API (with snapshot + dedup), candidate
  frontend portal, gating tests.
- **Phase 2 (P2)**: `sourcing_enabled` migration, skill/years extractor (built/used here), hybrid
  sourcing search service, invite/accept flow, company + candidate sourcing UI, gating tests.

## Complexity Tracking

No constitution violations requiring justification. The disciplined areas — cross-company CV
visibility (guarded by `open_to_work` + contact-hiding, with gating tests) and the LLM
skill/years extractor (schema-validated, never fabricates years, tested against messy CV
fixtures before ranking depends on it) — are handled within existing layers.
