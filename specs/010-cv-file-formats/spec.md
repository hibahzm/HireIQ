# Feature Specification: Additional CV File Formats (DOCX & Images)

**Feature Branch**: `010-cv-file-formats`

**Created**: 2026-06-07

**Status**: Draft

**Input**: V2-1 — accept DOCX and image (JPG/PNG) CVs in addition to PDF (deferred from MVP)

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Candidate Applies with a DOCX or Image CV (Priority: P1)

A candidate visits the job application page and uploads their CV as a Word document
(`.docx`) or an image (`.jpg`/`.png`) instead of a PDF. The system extracts the CV
content and screens it against the job criteria exactly as it does for PDFs — the
candidate sees the same confirmation, and the recruiter sees the same screening
result with no indication that a different file format was used.

**Why this priority**: Many candidates keep CVs as Word documents or photos. PDF-only
upload is a friction point that loses applicants. This is the entire scope of V2-1.

**Independent Test**: Submit a `.docx` and a `.png` CV to an active job. Within the
same SLA as PDF, the recruiter sees a screening score, rationale, and status for each.

**Acceptance Scenarios**:

1. **Given** an active job, **When** a candidate uploads a text-based `.docx` CV,
   **Then** the system extracts its text (paragraphs and tables) and produces a
   screening result.
2. **Given** an active job, **When** a candidate uploads a `.jpg` or `.png` CV,
   **Then** the system extracts the content via OCR and produces a screening result.
3. **Given** a `.docx` whose extracted text is too sparse to screen (e.g., mostly
   images), **When** the system processes it, **Then** it falls back to the OCR
   service and still produces a screening result.
4. **Given** a candidate uploads an unsupported format (e.g., `.txt`, `.rtf`,
   `.pages`), **When** they submit, **Then** the system rejects it with a clear
   error listing the supported formats; no application record is created.

---

### Edge Cases

- A corrupted or password-protected `.docx` is rejected immediately with a clear
  error; no application record is created (parity with the PDF corrupt-file rule).
- An image with no legible text (blank/blurry) yields an empty extraction → the
  upload is rejected with a "could not read CV" error; no application record created.
- File size cap (10 MB) applies identically across all formats; oversized uploads
  return the existing 413 Payload Too Large error.
- A file with a mismatched extension/MIME type (e.g., a PDF renamed to `.docx`) is
  rejected: the declared MIME type is checked against the allow-list, and extraction
  then fails to parse the bytes as the claimed type, yielding a 422 with no
  application record (rather than relying on the file extension alone).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Candidates MUST be able to upload a CV as `application/pdf`,
  `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (DOCX),
  `image/jpeg`, or `image/png`.
- **FR-002**: The system MUST extract text from DOCX files, including paragraph text
  and table contents.
- **FR-003**: The system MUST apply the same extraction-quality heuristic used for
  PDFs — when extracted text is below the quality threshold, it MUST fall back to the
  managed OCR/Document Intelligence path.
- **FR-004**: The system MUST extract image CVs (JPG/PNG) by routing them directly to
  the managed Document Intelligence path (no PDF/text-layer attempt).
- **FR-005**: The system MUST keep the existing 10 MB upload cap for all formats.
- **FR-006**: The system MUST reject unsupported formats with a clear error message
  that lists the accepted formats, and MUST NOT create an application record for a
  rejected upload (parity with FR-010 of the MVP).
- **FR-007**: Screening output (score, rationale, status) for DOCX and image CVs MUST
  be produced through the same pipeline and stored identically to PDF results — no
  format-specific fields are exposed to recruiters.
- **FR-008**: The public application form MUST advertise the accepted formats in its
  file input and helper text.

### Key Entities

No new entities. The `applications.cv_extraction_method` field already records which
extraction path was used (`pymupdf` vs. `document_intelligence`) and gains `docx` as a
source.

## Success Criteria *(mandatory)*

- **SC-001**: A DOCX or image CV produces a screening result within the same 2-minute
  SLA as a PDF for 95% of submissions (parity with MVP SC-002).
- **SC-002**: Extraction quality for DOCX and image CVs is sufficient that screening
  scores are comparable to the same CV submitted as PDF (no systematic degradation).
- **SC-003**: 100% of unsupported file formats are rejected with a clear message and
  leave no application record.

## Assumptions

- English-language CVs only (inherited from MVP).
- Multi-page image CVs are out of scope; a single image is treated as one CV.
- DOCX legacy `.doc` (binary Word 97–2003) is out of scope — `.docx` only.

## Dependencies

- Builds on the MVP screening pipeline (`OcrService`, `ScreeningService`, the public
  application endpoint, and `JobApplicationPage`).
- Adds a DOCX extraction library (e.g., `python-docx`) to the backend.
