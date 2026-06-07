# Data Model: Additional CV File Formats (Phase 1)

**No schema changes.** This feature widens an input path and reuses all existing
entities and tables from the MVP (`applications`, `candidates`, `cv_chunks`). No
migration is required.

## Affected field

### `applications.cv_extraction_method`

Existing free-text/enum-like column recording how the CV text was obtained. Today it
holds:

- `pymupdf` — PDF parsed via local text layer
- `document_intelligence` — scanned PDF (or sparse text) sent to Azure DI

This feature adds one possible value:

- `docx` — DOCX parsed locally via `python-docx`

(Image CVs and sparse DOCX fall back to `document_intelligence`, an existing value.)

**Validation / transitions**: unchanged. `cv_extraction_method` is set once by
`OcrService.extract` at ingestion and never mutated. Recruiter-facing views already
display it as-is; no enum constraint exists in the DB, so no migration is needed to
accept the new value.

## Out of scope

- No new columns, tables, indexes, or RLS policies.
- No change to `cv_chunks` shape, embedding dimensions, or hybrid-search behavior — the
  extracted text feeds the identical downstream pipeline regardless of source format.
