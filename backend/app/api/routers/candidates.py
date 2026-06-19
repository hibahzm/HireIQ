from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.cv_uploads import ACCEPTED_CV_TYPES, MAX_CV_SIZE, UNSUPPORTED_CV_MESSAGE
from app.api.deps import get_current_candidate
from app.db import _get_session_factory
from app.models.candidate import Candidate
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.candidate_cv_repository import CandidateCvRepository
from app.repositories.candidate_repository import CandidateRepository
from app.schemas.auth import CandidateResponse
from app.schemas.candidates import CandidateCvResponse, CandidateProfileUpdate
from app.services.cv_skill_extractor import run_skill_extraction_background
from app.services.embedding_service import EmbeddingService
from app.services.ocr_service import OcrService
from app.services.storage_service import StorageService
from app.services.usage_service import record_usage_events

logger = structlog.get_logger()

# Candidate account: profile + the single CV on file. Job-seeking actions
# (browse, apply, applications, invitations) live in candidate_jobs.py.
router = APIRouter(prefix="/candidate", tags=["candidates"])


@router.patch("/me", response_model=CandidateResponse)
async def update_me(
    body: CandidateProfileUpdate,
    candidate: Candidate = Depends(get_current_candidate),
):
    async with _get_session_factory()() as session:
        async with session.begin():
            updated = await CandidateRepository(session).update_profile(
                candidate_id=candidate.id,
                full_name=body.full_name,
                open_to_work=body.open_to_work,
            )
            has_cv = await CandidateCvRepository(session).exists(candidate.id)
            await AuditLogRepository(session).log_event(
                event_type="candidate.profile_updated",
                actor_type="candidate",
                actor_id=candidate.id,
                entity_type="candidate",
                entity_id=candidate.id,
                metadata={"open_to_work": updated.open_to_work},
            )
    return CandidateResponse(
        id=updated.id,
        email=updated.email,
        full_name=updated.full_name,
        is_active=updated.is_active,
        open_to_work=updated.open_to_work,
        has_cv=has_cv,
    )


@router.get("/cv", response_model=CandidateCvResponse)
async def get_cv(candidate: Candidate = Depends(get_current_candidate)):
    async with _get_session_factory()() as session:
        async with session.begin():
            cv = await CandidateCvRepository(session).get(candidate.id)
    if not cv:
        return CandidateCvResponse(has_cv=False)
    return CandidateCvResponse(
        has_cv=True,
        cv_extraction_method=cv["cv_extraction_method"],
        embedding_truncated=cv["embedding_truncated"],
        skills=cv["skills"] or [],
        updated_at=cv["updated_at"],
    )


@router.post("/cv", response_model=CandidateCvResponse, status_code=201)
async def upload_cv(
    cv_file: UploadFile = File(...),
    candidate: Candidate = Depends(get_current_candidate),
):
    """Store/replace the candidate's single CV: extract text, embed the WHOLE CV
    as one vector (token-capped, audit-logged on truncation), and upsert."""
    if cv_file.content_type not in ACCEPTED_CV_TYPES:
        raise HTTPException(status_code=422, detail=UNSUPPORTED_CV_MESSAGE)

    cv_bytes = await cv_file.read()
    if len(cv_bytes) > MAX_CV_SIZE:
        raise HTTPException(status_code=413, detail="CV file exceeds 10 MB limit")

    try:
        cv_text, extraction_method = await OcrService().extract(
            cv_bytes, filename=cv_file.filename or "cv", content_type=cv_file.content_type
        )
    except ValueError as exc:  # OcrValidationError subclasses ValueError
        raise HTTPException(status_code=422, detail=f"Invalid CV: {exc}")

    embedding, truncated, usage_event = await EmbeddingService().embed_whole_cv(cv_text)

    blob_ext = ACCEPTED_CV_TYPES[cv_file.content_type]
    blob_key = f"candidate-cvs/{candidate.id}/{uuid.uuid4()}{blob_ext}"
    await StorageService().upload(blob_key, cv_bytes)

    async with _get_session_factory()() as session:
        async with session.begin():
            await CandidateCvRepository(session).upsert(
                candidate_id=candidate.id,
                cv_blob_key=blob_key,
                cv_text=cv_text,
                cv_extraction_method=extraction_method,
                embedding=embedding,
                embedding_truncated=truncated,
            )
            await record_usage_events(session, company_id=None, events=[usage_event])
            if truncated:
                await AuditLogRepository(session).log_event(
                    event_type="candidate.cv.embedding_truncated",
                    actor_type="system",
                    entity_type="candidate",
                    entity_id=candidate.id,
                    metadata={"original_tokens": usage_event["metadata"]["original_tokens"]},
                )
            await AuditLogRepository(session).log_event(
                event_type="candidate.cv.uploaded",
                actor_type="candidate",
                actor_id=candidate.id,
                entity_type="candidate",
                entity_id=candidate.id,
            )

    # Fire-and-forget structured skill/years extraction (owns its own session).
    asyncio.create_task(run_skill_extraction_background(candidate_id=candidate.id, cv_text=cv_text))

    return CandidateCvResponse(
        has_cv=True,
        cv_extraction_method=extraction_method,
        embedding_truncated=truncated,
        skills=[],
    )
