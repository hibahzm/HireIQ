# Research: Additional CV File Formats (Phase 0)

## Decision 1 — DOCX text extraction library

**Decision**: Use `python-docx` to extract paragraph text and table cell text from
`.docx` files.

**Rationale**: `python-docx` is the de-facto standard for reading Office Open XML Word
documents, is pure-Python (no native build), reads paragraphs and tables (CVs often put
skills/experience in tables), and runs fast enough to stay within the async path. It
cannot read legacy binary `.doc` — acceptable, since the spec scopes to `.docx` only.

**Alternatives considered**:
- *Send DOCX straight to Azure Document Intelligence*: works but adds latency/cost for
  the common case where the DOCX has a clean text layer. Better to extract locally and
  fall back to DI only when sparse (mirrors the PDF strategy).
- *`docx2txt`*: simpler but ignores tables; loses structured CV content.
- *LibreOffice headless conversion to PDF*: heavyweight dependency, slow, overkill.

## Decision 2 — Image (JPG/PNG) extraction

**Decision**: Route image CVs directly to Azure Document Intelligence
(`prebuilt-document`); skip any local text-layer attempt.

**Rationale**: Images have no text layer, so PyMuPDF/python-docx don't apply. DI is
already wired into `OcrService._azure_doc_intelligence` and is the existing fallback for
scanned PDFs — reusing it keeps one OCR path and consistent quality.

**Alternatives considered**:
- *Local OCR (Tesseract)*: adds a native dependency and generally lower accuracy than
  DI for document layouts; rejected to avoid a second OCR stack.

## Decision 3 — Format dispatch

**Decision**: `OcrService.extract` dispatches on the file's type (extension/MIME):
PDF → existing PyMuPDF-then-DI path; DOCX → python-docx-then-DI (reusing `_quality_ok`);
image → DI directly. Quality heuristic (`word_count < 50` OR `printable_ratio < 0.90`)
is reused unchanged for the DOCX fallback decision.

**Rationale**: One entry point, minimal branching, reuses the existing quality gate and
DI client. Downstream (chunk/embed/screen/store) is untouched.

**Alternatives considered**:
- *Separate services per format*: unnecessary fragmentation for a small feature; the
  router would then need format logic, violating thin-handler guidance (Principle III).

## Decision 4 — Validation by content, not just extension

**Decision**: The application router validates the declared MIME type against the
allow-list and the `OcrService` raises `OcrValidationError` when the bytes don't parse
as the claimed type (e.g., a renamed file), yielding a 422 with no application record.

**Rationale**: Preserves the MVP's "no record for unreadable CV" guarantee (FR-006) and
prevents extension spoofing from creating bad data.
