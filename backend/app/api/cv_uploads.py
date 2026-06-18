"""Shared CV-upload constraints used by the public-apply and candidate routers."""

from __future__ import annotations

MAX_CV_SIZE = 10 * 1024 * 1024  # 10 MB

# Accepted CV content types (PDF + DOCX + JPG/PNG), mapped to a blob extension.
ACCEPTED_CV_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

UNSUPPORTED_CV_MESSAGE = "Unsupported file type. Accepted: PDF, DOCX, JPG, PNG."
