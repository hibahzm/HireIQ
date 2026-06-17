# Data Model: Candidate Accounts & In-App Talent Sourcing

All new/changed tables. `candidates` and `candidate_cvs` are **global (no RLS)** — they are not
owned by any company; cross-company visibility is enforced in the application layer
(`open_to_work = true`, contact details hidden until invitation acceptance).

## Migration 0020 — candidate accounts (Phase 1)

### `candidates` (extend existing global table)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | existing |
| `email` | text UNIQUE | existing — the single global identity / dedup anchor |
| `full_name` | text | existing |
| `password_hash` | text NULL | NEW — null for apply-time-only records (no account) |
| `is_active` | bool DEFAULT true | NEW |
| `open_to_work` | bool DEFAULT false | NEW — consent gate for sourcing (default OFF) |
| `created_at` | timestamptz | existing |
| `updated_at` | timestamptz DEFAULT now() | NEW (onupdate) |

A `candidates` row with `password_hash IS NULL` is an external/apply-only record; setting a
password "upgrades" the same row to an account (preserving the email-dedup invariant). No RLS.

### `candidate_cvs` (new global table — one row per candidate)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `candidate_id` | uuid FK→candidates UNIQUE | one current CV per candidate |
| `cv_blob_key` | text | stored original file |
| `cv_text` | text | extracted text (whole CV) |
| `cv_extraction_method` | text NULL | reuse OcrService method label |
| `embedding` | vector(1536) | **single whole-CV** embedding (not chunked) |
| `skills` | jsonb DEFAULT '[]' | `[{skill, years, years_basis, evidence}]` (populated Phase 2) |
| `tsv` | tsvector | full-text keyword index over cv_text |
| `embedding_truncated` | bool DEFAULT false | true if CV was shortened to fit token cap |
| `created_at` / `updated_at` | timestamptz | |

Indexes (mirror `0004` cv_chunks DDL): `ivfflat (embedding vector_cosine_ops)`, `GIN (tsv)`,
unique on `candidate_id`. **No RLS.** Upsert on `candidate_id` so re-upload replaces the row.

## Migration 0021 — job sourcing (Phase 2)

### `jobs` (extend)

| Column | Type | Notes |
|---|---|---|
| `sourcing_enabled` | bool DEFAULT false | NEW — per-job opt-in to in-app sourcing |

## Reused entities (unchanged schema)

- **`applications`**: still `(job_id, candidate_id)` UNIQUE; carries `cv_blob_key` + `cv_text`
  snapshot used by screening. Account apply copies the CV onto the application at apply time.
- **`job_criteria`**: required/optional skills + `experience_level` — the matching target for
  the experience-aware ranking.
- **`cv_chunks` / `job_chunks`**: the existing company-scoped screening index — **untouched**.

## Structured skills JSON (in `candidate_cvs.skills`)

```json
[
  { "skill": "node.js", "years": 3.0, "years_basis": "stated", "evidence": "Node.js (3 years)" },
  { "skill": "react", "years": 2.0, "years_basis": "inferred_from_dates", "evidence": "2019–2021 React dev" },
  { "skill": "graphql", "years": null, "years_basis": "unknown", "evidence": "extensive experience with GraphQL" }
]
```

`years_basis`: `stated` (explicit in CV) | `inferred_from_dates` (computed from employment dates)
| `unknown` (present but unquantified — never assigned a fabricated number). Skill names are
canonicalized (Node/NodeJS/node.js → `node.js`). Ranking treats `unknown`/`null` years as a soft
miss and may weight `stated` above `inferred_from_dates`.

## Migration 0022 — sourcing invitations (Phase 2, as built)

A dedicated entity was needed: an application requires a CV snapshot (`cv_blob_key NOT NULL`) and
should only exist after the candidate consents, so a pending invitation can't be a half-formed
application. New **global (no-RLS)** table `sourcing_invitations`:

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `job_id` | uuid FK→jobs | |
| `candidate_id` | uuid FK→candidates | |
| `company_id` | uuid FK→companies | |
| `status` | text DEFAULT 'pending' | `pending`/`accepted`/`declined`/`expired` (CHECK) |
| `message` | text NULL | optional note from the company |
| `created_at`/`updated_at`/`responded_at` | timestamptz | |

UNIQUE `(job_id, candidate_id)`. Global, like `candidates`/`candidate_cvs` — access enforced in
the app layer (company endpoints filter by `company_id`, candidate endpoints by `candidate_id`).
On **accept**, it routes through the normal deduplicated apply path (CV snapshot → application,
one per job per email) and the invitation is marked `accepted`.

## Migration 0023 — candidate application resolvers (Phase 2, as built)

`applications` has company-only FORCE RLS, so a candidate (no company context) can't read their own
applications across companies. Two SECURITY DEFINER, candidate-scoped resolvers (same pattern as
the 0015–0017 token resolvers) back the candidate-facing reads:
`candidate_list_applications(candidate_id)` and `candidate_applied_job_ids(candidate_id)`.
