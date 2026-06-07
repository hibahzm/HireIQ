# API Contract Delta: Additional CV File Formats (Phase 1)

This is a **delta** on the MVP application-upload endpoint. Everything not listed here
is unchanged from [the MVP api contract](../../001-ai-hiring-platform/contracts/api.md).

## `POST /jobs/{job_id}/applications` (public, multipart)

Submit a candidate application with a CV file. The only change is the set of accepted
CV content types.

### Request (multipart/form-data)

| Field | Type | Notes |
|-------|------|-------|
| `full_name` | string | unchanged |
| `email` | string | unchanged |
| `cv_file` | file | **Accepted types (widened)**: see below. Max size **10 MB** (unchanged). |

**Accepted `cv` content types**:

| Format | MIME type |
|--------|-----------|
| PDF (existing) | `application/pdf` |
| DOCX (new) | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| JPEG (new) | `image/jpeg` |
| PNG (new) | `image/png` |

### Responses

| Status | When | Body |
|--------|------|------|
| `201 Created` | Valid file accepted; screening enqueued | `ApplicationResponse` JSON — includes `id`, `status`, `screening_status`, and `cv_extraction_method` (unchanged from MVP) |
| `409 Conflict` | Duplicate (same email + job) | unchanged |
| `422 Unprocessable Entity` | **Unsupported format**, or file unreadable/corrupt/encrypted (any format) | `{ "detail": "Unsupported file type. Accepted: PDF, DOCX, JPG, PNG." }` — **no application record created** |
| `413 Payload Too Large` | File exceeds 10 MB | unchanged |
| `429 Too Many Requests` | Rate limit (5/IP/hr) | unchanged |

### Behavior notes

- Extraction is dispatched by type: PDF → local text-then-DI; DOCX → `python-docx`
  then DI on sparse text; image → Azure Document Intelligence directly.
- The resulting screening object (`screening_score`, `screening_rationale`,
  `screening_status`) is produced by the same pipeline and is **format-agnostic** in
  the response — recruiters see no format-specific fields beyond the existing
  `cv_extraction_method` (which may now be `docx`).
