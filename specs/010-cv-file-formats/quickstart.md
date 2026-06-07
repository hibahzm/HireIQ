# Quickstart Validation: Additional CV File Formats

Validates V2-1 end-to-end. Assumes the MVP stack is running (see the
[MVP quickstart](../../001-ai-hiring-platform/quickstart.md)) and an **active job**
exists with id `$JOB_ID`.

## Prerequisites

- Running stack (`docker compose -f infra/docker-compose.yml up -d`).
- An active job accepting applications.
- Sample CVs: a `.docx`, a `.jpg`/`.png`, and (for the negative case) a `.txt`.
- Azure Document Intelligence configured (or local fallback) for the image path.

## Scenario 1 — DOCX upload

```bash
curl -X POST http://localhost:8000/jobs/$JOB_ID/applications \
  -F "full_name=Dana Doc" \
  -F "email=dana@example.com" \
  -F "cv=@/path/to/cv.docx;type=application/vnd.openxmlformats-officedocument.wordprocessingml.document"
```

**Expected**: `202` with `application_id`. Within ~2 min, `GET /applications/{id}`
shows a `screening_score`, `screening_rationale`, and `screening_status`;
`cv_extraction_method` is `docx` (or `document_intelligence` if the DOCX was sparse).

## Scenario 2 — Image (PNG/JPG) upload

```bash
curl -X POST http://localhost:8000/jobs/$JOB_ID/applications \
  -F "full_name=Ivan Image" \
  -F "email=ivan@example.com" \
  -F "cv=@/path/to/cv.png;type=image/png"
```

**Expected**: `202`; screening completes within ~2 min; `cv_extraction_method` is
`document_intelligence`.

## Scenario 3 — Unsupported format rejected

```bash
curl -X POST http://localhost:8000/jobs/$JOB_ID/applications \
  -F "full_name=Terry Text" \
  -F "email=terry@example.com" \
  -F "cv=@/path/to/cv.txt;type=text/plain"
```

**Expected**: `422` with a clear "Accepted: PDF, DOCX, JPG, PNG" message. Verify **no
application record** was created (`GET /jobs/$JOB_ID/applications` does not list Terry).

## Scenario 4 — Corrupt / sparse files

- Upload a corrupt or password-protected `.docx` → `422`, no record (parity with PDF).
- Upload a blank/blurry image with no legible text → `422` ("could not read CV").

## Scenario 5 — Parity check

Submit the **same CV** as PDF and as DOCX. **Expected**: comparable `screening_score`
and a rationale referencing the same skills — no systematic degradation (SC-002).

## Frontend check

Open the public application page for the job. **Expected**: the file picker advertises
PDF, DOCX, JPG, PNG, and the helper text lists them; selecting an unsupported file is
rejected with a clear message.
