# Data Model: HireIQ — AI-Powered Hiring Platform (MVP)

**Feature**: 001-ai-hiring-platform | **Date**: 2026-06-04

All tenant-scoped tables carry a `company_id UUID NOT NULL` column and a corresponding RLS policy:

```sql
CREATE POLICY tenant_isolation ON <table>
  USING (company_id = current_setting('app.current_company_id')::uuid);
```

The `audit_logs` and `candidates` tables are intentionally excluded from standard RLS — see notes per entity.

---

## Entities

### 1. `companies`

Root tenant entity. Not RLS-scoped (it's the tenant itself).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `name` | `TEXT` | NOT NULL | Company display name |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**No RLS policy** — company rows are public to authenticated users; individual company data is isolated by the `company_id` FK on all child tables.

---

### 2. `users`

Recruiters and admins belonging to a company.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `company_id` | `UUID` | NOT NULL, FK → companies | RLS column |
| `email` | `TEXT` | NOT NULL, UNIQUE | Case-insensitive enforce via `citext` or lower() |
| `password_hash` | `TEXT` | NOT NULL | bcrypt |
| `role` | `TEXT` | NOT NULL, CHECK IN ('admin','recruiter') | |
| `is_active` | `BOOL` | NOT NULL, default true | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**RLS**: `company_id = current_setting('app.current_company_id')::uuid`

**Indexes**: `(company_id, email)` UNIQUE (scoped dedup); `email` UNIQUE (global login lookup — uses BYPASSRLS context)

---

### 3. `jobs`

A role a company is hiring for.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `company_id` | `UUID` | NOT NULL, FK → companies | RLS column |
| `title` | `TEXT` | NOT NULL | |
| `status` | `TEXT` | NOT NULL, CHECK IN ('draft','setup','active','paused','closed'), default 'draft' | |
| `created_by` | `UUID` | NOT NULL, FK → users | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**State machine**: `draft → setup → active → paused ↔ active → closed`
- `draft`: just created; criteria not yet elicited
- `setup`: setup conversation in progress
- `active`: criteria confirmed; accepting applications
- `paused`: temporarily closed to new applications; existing applications continue
- `closed`: no new applications; all processing stops

**RLS**: standard tenant isolation

**Indexes**: `(company_id, status)` for dashboard queries

---

### 4. `job_criteria`

The structured evaluation framework for a job. One-to-one with `jobs`. Created when the setup conversation completes.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `job_id` | `UUID` | NOT NULL, UNIQUE, FK → jobs | One criteria per job |
| `company_id` | `UUID` | NOT NULL, FK → companies | RLS column |
| `required_skills` | `JSONB` | NOT NULL, default '[]' | Array of `{skill: string, priority: 'required'}` |
| `optional_skills` | `JSONB` | NOT NULL, default '[]' | Array of `{skill: string, priority: 'nice_to_have'}` |
| `experience_level` | `TEXT` | NOT NULL | e.g., 'junior', 'mid', 'senior', 'lead' |
| `min_years_experience` | `SMALLINT` | NULLABLE | Numeric floor; null = unspecified |
| `evaluation_dimensions` | `JSONB` | NOT NULL | Array of `{name: string, weight: number, description: string}`; weights MUST sum to 1.0 |
| `dealbreakers` | `JSONB` | NOT NULL, default '[]' | Array of strings (automatic rejection conditions) |
| `min_screening_score` | `SMALLINT` | NOT NULL, CHECK (0–100) | Recruiter-set threshold; candidates at/above = qualified |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**RLS**: standard tenant isolation

---

### 5. `setup_conversations`

AI-guided setup conversation history. One per job (created when setup begins).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `job_id` | `UUID` | NOT NULL, UNIQUE, FK → jobs | |
| `company_id` | `UUID` | NOT NULL, FK → companies | RLS column |
| `messages` | `JSONB` | NOT NULL, default '[]' | Array of `{role: 'user'|'assistant', content: string}` |
| `status` | `TEXT` | NOT NULL, CHECK IN ('in_progress','completed'), default 'in_progress' | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**RLS**: standard tenant isolation

---

### 6. `candidates`

A person applying for jobs. Identified globally by email; not RLS-scoped at this level.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `email` | `TEXT` | NOT NULL, UNIQUE | Global uniqueness — one candidate record per email |
| `full_name` | `TEXT` | NOT NULL | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**No RLS policy** — candidates are global; tenant isolation is enforced via `applications` (which is RLS-scoped). Candidate lookups from the api service always JOIN through an `applications` record that is RLS-scoped, preventing cross-tenant access.

**Indexes**: `email` UNIQUE

---

### 7. `applications`

A candidate's submission for a specific job. Core junction between candidates and jobs.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `job_id` | `UUID` | NOT NULL, FK → jobs | |
| `candidate_id` | `UUID` | NOT NULL, FK → candidates | |
| `company_id` | `UUID` | NOT NULL, FK → companies | RLS column |
| `cv_blob_key` | `TEXT` | NOT NULL | Blob storage object key for original CV file |
| `cv_text` | `TEXT` | NULLABLE | Extracted CV text (NULL until extraction completes) |
| `cv_extraction_method` | `TEXT` | NULLABLE, CHECK IN ('pymupdf','document_intelligence') | Set after extraction |
| `screening_score` | `SMALLINT` | NULLABLE, CHECK (0–100) | NULL until screening completes |
| `screening_rationale` | `TEXT` | NULLABLE | LLM-generated rationale (PII-redacted) |
| `screening_status` | `TEXT` | NOT NULL, CHECK IN ('pending','qualified','rejected'), default 'pending' | |
| `interview_token` | `UUID` | NULLABLE | Set when interview invitation is generated |
| `interview_token_expires_at` | `TIMESTAMPTZ` | NULLABLE | 7 days after invitation sent |
| `status` | `TEXT` | NOT NULL, CHECK IN ('applied','screening','qualified','rejected','invited','interviewing','evaluated','archived'), default 'applied' | Full application lifecycle |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**State machine**: `applied → screening → qualified/rejected → invited → interviewing → evaluated → archived`

**Constraints**: `UNIQUE (job_id, candidate_id)` — enforces FR-013 (no duplicate applications per job)

**Validation**: A job application at the same company for a *different* job creates a new `applications` row (per spec assumption — each job is independent).

**RLS**: standard tenant isolation

**Indexes**: `(job_id, screening_status)` for filtering; `interview_token` for WebSocket connect lookup (non-RLS query)

---

### 8. `interview_sessions`

A single AI-conducted interview session for one application.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `application_id` | `UUID` | NOT NULL, UNIQUE, FK → applications | One session per application |
| `company_id` | `UUID` | NOT NULL, FK → companies | RLS column |
| `mode` | `TEXT` | NOT NULL, CHECK IN ('voice','text') | Voice with text fallback |
| `status` | `TEXT` | NOT NULL, CHECK IN ('pending','in_progress','completed','expired','system_interrupted','abandoned'), default 'pending' | |
| `turn_count` | `SMALLINT` | NOT NULL, default 0 | Number of candidate turns completed |
| `max_turns` | `SMALLINT` | NOT NULL, default 20 | Configurable max turns per job |
| `last_active_at` | `TIMESTAMPTZ` | NULLABLE | Updated on every turn; used to detect 24h expiry |
| `started_at` | `TIMESTAMPTZ` | NULLABLE | Set when first turn begins |
| `completed_at` | `TIMESTAMPTZ` | NULLABLE | Set when session reaches terminal state |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**State machine**:
- `pending → in_progress` (candidate connects)
- `in_progress → completed` (all dimensions covered OR max_turns reached)
- `in_progress → system_interrupted` (AI service unavailable)
- `in_progress → abandoned` (>24h since last_active_at with no reconnect after system_interrupted or spontaneous disconnect)
- `system_interrupted → in_progress` (candidate reconnects within 24h)

**Resume logic**: Session state (LangGraph InterviewState) is stored in Redis at `interview_session:{session_id}` with a 25h TTL. On reconnect, api loads Redis state and continues from `turn_count`.

**RLS**: standard tenant isolation

---

### 9. `interview_messages`

A single turn in an interview. Immutable once created.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `session_id` | `UUID` | NOT NULL, FK → interview_sessions | |
| `company_id` | `UUID` | NOT NULL, FK → companies | RLS column |
| `turn_index` | `SMALLINT` | NOT NULL | 0-based; `(session_id, turn_index)` UNIQUE |
| `speaker` | `TEXT` | NOT NULL, CHECK IN ('candidate','ai') | |
| `content_text` | `TEXT` | NOT NULL | PII-redacted before storage |
| `audio_blob_key` | `TEXT` | NULLABLE | Blob storage key for audio recording (candidate turns only) |
| `is_blocked` | `BOOL` | NOT NULL, default false | True if guardrail blocked the turn; content_text set to '[blocked]' |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**Constraints**: `UNIQUE (session_id, turn_index)`

**Note on blocked turns**: When `is_blocked = true`, `content_text` stores `'[blocked]'` rather than the original input (FR-023: blocked content MUST NOT be stored).

**RLS**: standard tenant isolation

---

### 10. `evaluations`

AI-generated assessment of a candidate's complete interview. Created after interview completion.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `application_id` | `UUID` | NOT NULL, UNIQUE, FK → applications | One evaluation per application |
| `company_id` | `UUID` | NOT NULL, FK → companies | RLS column |
| `overall_score` | `SMALLINT` | NOT NULL, CHECK (0–100) | |
| `recommendation` | `TEXT` | NOT NULL, CHECK IN ('hire','no_hire','uncertain') | |
| `dimension_scores` | `JSONB` | NOT NULL | Array of `{dimension: string, score: number, evidence_quotes: string[]}` |
| `consistency_flags` | `JSONB` | NOT NULL, default '[]' | Array of `{claim: string, cv_statement: string, interview_statement: string, flag_type: 'contradiction'|'unverified'}` |
| `communication_quality` | `JSONB` | NOT NULL | `{response_depth: number, filler_word_frequency: number, deflection_frequency: number}` |
| `confidence_flag` | `BOOL` | NOT NULL, default false | True when evidence quality is below threshold |
| `confidence_reason` | `TEXT` | NULLABLE | Explanation when confidence_flag is true |
| `summary` | `TEXT` | NULLABLE | LLM-generated strengths + areas-for-improvement summary (PII-redacted); required by FR-033 for candidate feedback report |
| `feedback_token` | `UUID` | NULLABLE | Set when candidate feedback email is sent |
| `feedback_token_expires_at` | `TIMESTAMPTZ` | NULLABLE | 30 days after evaluation |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**RLS**: standard tenant isolation

**Indexes**: `(company_id, overall_score DESC)` for ranked shortlist queries; `feedback_token` for public feedback endpoint

---

### 11. `cv_chunks`

Chunked CV text with vector embeddings for hybrid search. One application → many chunks.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `application_id` | `UUID` | NOT NULL, FK → applications | |
| `company_id` | `UUID` | NOT NULL, FK → companies | RLS column |
| `chunk_index` | `SMALLINT` | NOT NULL | Ordering within document |
| `chunk_text` | `TEXT` | NOT NULL | |
| `embedding` | `vector(1536)` | NOT NULL | text-embedding-3-small output |
| `tsv` | `TSVECTOR` | NOT NULL | Generated from chunk_text via `to_tsvector('english', chunk_text)` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**Indexes**:
- `ivfflat (embedding vector_cosine_ops) WITH (lists = 100)` (dense search)
- `GIN (tsv)` (sparse / keyword search)

**RLS**: standard tenant isolation

---

### 12. `job_chunks`

Chunked job criteria text for embedding-based matching. One job → few chunks (criteria description).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `job_id` | `UUID` | NOT NULL, FK → jobs | |
| `company_id` | `UUID` | NOT NULL, FK → companies | RLS column |
| `chunk_index` | `SMALLINT` | NOT NULL | |
| `chunk_text` | `TEXT` | NOT NULL | Serialized from job_criteria fields |
| `embedding` | `vector(1536)` | NOT NULL | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**Indexes**: `ivfflat (embedding vector_cosine_ops) WITH (lists = 50)`

**RLS**: standard tenant isolation

---

### 13. `audit_logs`

Immutable compliance and debugging record. Append-only.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default gen_random_uuid() | |
| `company_id` | `UUID` | NULLABLE | NULL for system events with no tenant context |
| `actor_id` | `UUID` | NULLABLE | user.id or NULL for system/candidate actions |
| `actor_type` | `TEXT` | NOT NULL, CHECK IN ('system','user','candidate') | |
| `event_type` | `TEXT` | NOT NULL | e.g., `cv.screening.started`, `interview.turn.blocked`, `evaluation.generated` |
| `entity_type` | `TEXT` | NULLABLE | e.g., `application`, `interview_session` |
| `entity_id` | `UUID` | NULLABLE | ID of the affected entity |
| `metadata` | `JSONB` | NOT NULL, default '{}' | Event-specific payload (PII-redacted) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default now() | |

**No UPDATE/DELETE** — insert-only via a `RESTRICT` trigger or application-level convention.

**RLS**: Not enforced at row level. Access restricted by role — only admin users or the system can query audit_logs. Recruiters do not have direct access.

---

## Relationships

```text
companies
  └─< users
  └─< jobs
        └── job_criteria (1:1)
        └── setup_conversations (1:1)
        └─< applications
              ├── candidate (N:1)
              ├─< cv_chunks
              └── interview_sessions (1:1)
                    └─< interview_messages
              └── evaluations (1:1)
        └─< job_chunks
```

---

## Global State Machines

### Application Status

```
applied
  └→ screening           (extraction + screening job queued)
       └→ qualified       (score ≥ min_screening_score)
       └→ rejected        (score < min_screening_score)
            └→ invited    (recruiter triggers invitation)
                 └→ interviewing   (candidate connects)
                       └→ evaluated        (interview complete + evaluation generated)
                             └→ archived
```

### Interview Session Status

```
pending
  └→ in_progress            (first WebSocket connection received)
       └→ completed          (all dimensions explored OR max_turns reached)
       └→ system_interrupted (AI service unavailable)
            └→ in_progress   (reconnect within 24h)
            └→ abandoned     (>24h with no reconnect)
       └→ abandoned          (candidate disconnects and never reconnects within 24h)
```

---

## Migration Notes

- Alembic migration user must have `BYPASSRLS` privilege to run DDL migrations on RLS-enabled tables.
- `candidates` and `audit_logs` are excluded from the standard `tenant_isolation` RLS policy — explicit note in each migration.
- pgvector extension must be enabled before cv_chunks / job_chunks migration: `CREATE EXTENSION IF NOT EXISTS vector;`
- `tsv` column on `cv_chunks` should be a generated column: `GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED`
