# Tasks: Additional CV File Formats (DOCX & Images)

**Input**: Design documents from `specs/010-cv-file-formats/`

**Prerequisites**: [plan.md](plan.md) · [spec.md](spec.md) · [research.md](research.md) · [data-model.md](data-model.md) · [contracts/api.md](contracts/api.md) · [quickstart.md](quickstart.md)

**Tests**: CV screening is a Constitution Principle VIII TDD-mandated domain, so the
extraction/validation tests below are written FIRST and confirmed failing before the
corresponding implementation tasks.

> This is the scoped task list for V2-1 (Phase 9 of the overall roadmap). Tasks are
> numbered T001–T008 within this feature and build entirely on the existing MVP
> screening pipeline.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared in-progress dependencies)
- **[Story]**: `US1` maps to User Story 1 in [spec.md](spec.md)
- Exact file paths are included in every description

---

## Phase 1: Setup

- [ ] T001 [P] Add `python-docx` to `backend/pyproject.toml` dependencies (DOCX extraction); rebuild the backend image / reinstall deps

---

## Phase 2: Foundational (Blocking Prerequisites)

**None.** This feature reuses the existing MVP ingestion pipeline (`OcrService`,
`ScreeningService`, the public application endpoint, `cv_chunks`, hybrid search). No
schema migration, new service, or new endpoint is required.

---

## Phase 3: User Story 1 — Candidate Applies with a DOCX or Image CV (Priority: P1) 🎯

**Goal**: Accept `.docx` and `.jpg`/`.png` CVs and produce screening results identical
to PDFs; reject unsupported formats with no application record.

**Independent Test**: Submit a `.docx` and a `.png` CV to an active job → within ~2 min
the recruiter sees a screening score/rationale/status for each; a `.txt` upload returns
422 with no record. See [quickstart.md](quickstart.md).

### Tests for User Story 1 (Constitution VIII — write FIRST, confirm FAILING before T005)

- [ ] T002 [P] [US1] Write failing integration test: DOCX CV upload → extraction + screening in `backend/tests/integration/test_cv_formats.py` — asserts a `.docx` (paragraphs + a table) yields a non-empty `cv_text`, a screening score/rationale, and `cv_extraction_method == "docx"` (mock the agents/LLM call); a sparse/text-light `.docx` falls back to `document_intelligence`
- [ ] T003 [P] [US1] Write failing integration test: image + unsupported handling in `backend/tests/integration/test_cv_formats.py` — a `.png`/`.jpg` CV routes to `document_intelligence` and produces a screening result; a blank/blurry image with no legible text yields an empty extraction → 422 "could not read CV" with NO application record (the `no_text_extracted` branch); a `.txt` upload returns 422 with a clear message and creates NO application record; a renamed/corrupt file returns 422

### Implementation for User Story 1

- [ ] T004 [US1] Add DOCX extraction to `OcrService` in `backend/app/services/ocr_service.py` — `_try_docx(file_bytes)` using `python-docx` to read paragraph text and table cell text; run the synchronous `python-docx` parse via `anyio.to_thread.run_sync` so the CPU-bound parse does not block the event loop (Constitution Principle II); raise `OcrValidationError` on corrupt/unreadable DOCX; reuse the existing `_quality_ok` heuristic to fall back to `_azure_doc_intelligence` when text is sparse; return `(text, "docx")`
- [ ] T005 [US1] Add format dispatch + image routing in `OcrService.extract` in `backend/app/services/ocr_service.py` — dispatch on the file type (extension/MIME from `filename`): PDF → existing PyMuPDF-then-DI path; DOCX → `_try_docx`-then-DI; image (`.jpg`/`.jpeg`/`.png`) → `_azure_doc_intelligence` directly; unknown type → `OcrValidationError`
- [ ] T006 [US1] Widen accepted CV content types in `backend/app/api/routers/applications.py` — accept `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `image/jpeg`, `image/png`; keep the 10 MB cap; return 422 with "Accepted: PDF, DOCX, JPG, PNG." for unsupported types; ensure no application record is created on rejection (parity with FR-006)
- [ ] T007 [US1] Update `JobApplicationPage` in `frontend/src/pages/applications/JobApplicationPage.tsx` — set the file input `accept=".pdf,.docx,.jpg,.jpeg,.png"` (and matching MIME types) and update helper text to list all supported formats

**Checkpoint**: DOCX and image CVs produce screening results at the same quality/SLA as
PDF (SC-001/SC-002); unsupported formats return 422 with no record (SC-003). Tests
T002/T003 pass.

---

## Phase 4: Polish & Cross-Cutting

- [ ] T008 [P] Validate parity per [quickstart.md](quickstart.md) §Scenario 5 — submit the same CV as PDF and DOCX, confirm comparable screening scores and that the rationale references the same skills (no systematic degradation, SC-002); also confirm each new-format submission completes within the ≤ 2 min screening SLA (SC-001)

---

## Dependencies & Execution Order

- **Phase 1 (Setup)**: T001 first — `python-docx` must be installed before extraction code/tests run.
- **Phase 3 (US1)**: Tests T002/T003 written and failing before implementation T004–T007.
  - T004 (DOCX extraction) before T005 (dispatch wires it in).
  - T005 before T006 is not strictly required (different files) but the router relies on `OcrService` accepting the new types.
  - T007 (frontend) is independent of the backend tasks.
- **Phase 4 (Polish)**: After US1 implementation is complete.

### Parallel Opportunities

- T002 and T003 (tests, same new file — write together but they are independent cases).
- T007 (frontend) can proceed in parallel with backend T004–T006.

---

## Implementation Strategy

This is a single-user-story feature. Deliver US1 end-to-end:

1. Phase 1: add `python-docx`.
2. Write failing tests (T002/T003).
3. Implement extraction + dispatch (T004/T005), router validation (T006), frontend (T007).
4. Validate parity (T008) and run the quickstart scenarios.

---

## Notes

- No DB migration, no new endpoint, no new entity — `cv_extraction_method` simply gains
  the value `docx` (see [data-model.md](data-model.md)).
- Everything downstream of extraction (chunk → embed → hybrid search → screen → store)
  is unchanged, which is what guarantees screening parity across formats.
- Out of scope: legacy `.doc`, multi-page image CVs, non-English CVs.
