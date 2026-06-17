from __future__ import annotations

import asyncio
import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_current_candidate
from app.db import _get_session_factory
from app.models.candidate import Candidate
from app.repositories.application_repository import ApplicationRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.candidate_cv_repository import CandidateCvRepository
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.sourcing_invitation_repository import SourcingInvitationRepository
from app.schemas.auth import CandidateResponse
from app.schemas.candidates import (
    CandidateApplicationResponse,
    CandidateCvResponse,
    CandidateInvitation,
    CandidateProfileUpdate,
    OpenJobResponse,
)
from app.services.cv_skill_extractor import run_skill_extraction_background
from app.services.embedding_service import EmbeddingService
from app.services.ocr_service import OcrService
from app.services.screening_service import run_screening_background
from app.services.storage_service import StorageService
from app.services.usage_service import record_usage_events

logger = structlog.get_logger()

router = APIRouter(prefix="/candidate", tags=["candidates"])

MAX_CV_SIZE = 10 * 1024 * 1024  # 10 MB
ACCEPTED_CV_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
UNSUPPORTED_CV_MESSAGE = "Unsupported file type. Accepted: PDF, DOCX, JPG, PNG."


# ── profile ──────────────────────────────────────────────────────────────────


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


# ── CV ───────────────────────────────────────────────────────────────────────


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
    asyncio.create_task(
        run_skill_extraction_background(candidate_id=candidate.id, cv_text=cv_text)
    )

    return CandidateCvResponse(
        has_cv=True,
        cv_extraction_method=extraction_method,
        embedding_truncated=truncated,
        skills=[],
    )


# ── browse & apply ───────────────────────────────────────────────────────────


@router.get("/jobs", response_model=list[OpenJobResponse])
async def browse_open_jobs(candidate: Candidate = Depends(get_current_candidate)):
    """List jobs open for applications (public_read_active_jobs policy)."""
    async with _get_session_factory()() as session:
        async with session.begin():
            rows = (
                (
                    await session.execute(
                        sa.text(
                            """
                            SELECT j.id, j.title, j.description, j.created_at,
                                   co.name AS company_name
                            FROM jobs j
                            LEFT JOIN companies co ON co.id = j.company_id
                            WHERE j.status = 'active'
                            ORDER BY j.created_at DESC
                            """
                        )
                    )
                )
                .mappings()
                .all()
            )
            # Which of these the candidate already applied to (RLS-bypassing,
            # candidate-scoped resolver).
            applied = {
                str(r[0])
                for r in (
                    await session.execute(
                        sa.text("SELECT * FROM candidate_applied_job_ids(:cid)"),
                        {"cid": candidate.id},
                    )
                ).all()
            }
    return [
        OpenJobResponse(
            id=str(r["id"]),
            title=r["title"],
            description=r["description"],
            company_name=r["company_name"],
            created_at=r["created_at"],
            already_applied=str(r["id"]) in applied,
        )
        for r in rows
    ]


@router.get("/applications", response_model=list[CandidateApplicationResponse])
async def my_applications(candidate: Candidate = Depends(get_current_candidate)):
    async with _get_session_factory()() as session:
        async with session.begin():
            # SECURITY DEFINER resolver: candidate-scoped read across companies
            # (applications has company-only RLS, so a direct SELECT sees nothing).
            rows = (
                (
                    await session.execute(
                        sa.text("SELECT * FROM candidate_list_applications(:cid)"),
                        {"cid": candidate.id},
                    )
                )
                .mappings()
                .all()
            )
    return [
        CandidateApplicationResponse(
            id=str(r["id"]),
            job_id=str(r["job_id"]),
            job_title=r["job_title"],
            company_name=r["company_name"],
            status=r["status"],
            screening_status=r["screening_status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


async def _apply_with_stored_cv(
    session,
    *,
    candidate: Candidate,
    job_id: str,
    company_id: str,
    job_title: str,
    source: str,
) -> CandidateApplicationResponse:
    """Create a deduplicated application from the candidate's stored CV.

    Assumes the session already has RLS context set to `company_id`. Snapshots the
    stored CV blob onto a per-application key so the unchanged screening pipeline
    reads it exactly like an external apply, and later CV edits never alter a past
    screening. Raises HTTPException on dedup (409) or missing CV (422).
    """
    app_repo = ApplicationRepository(session)
    if await app_repo.get_by_job_and_email(job_id, candidate.email):
        raise HTTPException(status_code=409, detail="You have already applied to this job")

    cv = await CandidateCvRepository(session).get(candidate.id)
    if not cv:
        raise HTTPException(status_code=422, detail="Upload a CV to your profile before applying")

    src_key = cv["cv_blob_key"]
    ext = src_key[src_key.rfind(".") :] if "." in src_key else ""
    snapshot_key = f"cvs/{job_id}/{uuid.uuid4()}{ext}"
    storage = StorageService()
    cv_bytes = await storage.download(src_key)
    await storage.upload(snapshot_key, cv_bytes)

    application = await app_repo.create(
        job_id=job_id,
        candidate_id=candidate.id,
        company_id=company_id,
        cv_blob_key=snapshot_key,
    )
    await AuditLogRepository(session).log_event(
        event_type="application.created",
        actor_type="candidate",
        actor_id=candidate.id,
        entity_type="application",
        entity_id=application.id,
        company_id=company_id,
        metadata={"source": source},
    )
    return CandidateApplicationResponse(
        id=str(application.id),
        job_id=job_id,
        job_title=job_title,
        status=application.status,
        screening_status=application.screening_status,
        created_at=application.created_at,
    )


@router.post("/jobs/{job_id}/apply", response_model=CandidateApplicationResponse, status_code=201)
async def apply_to_job(
    job_id: str,
    candidate: Candidate = Depends(get_current_candidate),
):
    """One-click apply with the candidate's stored CV (deduplicated per job per email)."""
    async with _get_session_factory()() as session:
        async with session.begin():
            # Read the active job WITHOUT RLS (public_read_active_jobs policy).
            job_row = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT id, company_id, title, status FROM jobs "
                            "WHERE id = :id AND status = 'active'"
                        ),
                        {"id": job_id},
                    )
                )
                .mappings()
                .first()
            )
            if not job_row:
                raise HTTPException(
                    status_code=404, detail="Job not found or not accepting applications"
                )
            company_id = str(job_row["company_id"])
            await session.execute(
                sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                {"cid": company_id},
            )
            response = await _apply_with_stored_cv(
                session,
                candidate=candidate,
                job_id=job_id,
                company_id=company_id,
                job_title=str(job_row["title"]),
                source="candidate_account",
            )

    asyncio.create_task(
        run_screening_background(
            application_id=response.id,
            company_id=company_id,
            job_id=job_id,
            job_title=response.job_title or "",
            candidate_email=candidate.email,
        )
    )
    return response


# ── sourcing invitations ─────────────────────────────────────────────────────


@router.get("/invitations", response_model=list[CandidateInvitation])
async def my_invitations(candidate: Candidate = Depends(get_current_candidate)):
    async with _get_session_factory()() as session:
        async with session.begin():
            rows = await SourcingInvitationRepository(session).list_for_candidate(candidate.id)
    return [
        CandidateInvitation(
            id=str(r["id"]),
            job_id=str(r["job_id"]),
            job_title=r["job_title"],
            company_name=r["company_name"],
            status=r["status"],
            message=r["message"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.post(
    "/invitations/{invitation_id}/accept",
    response_model=CandidateApplicationResponse,
    status_code=201,
)
async def accept_invitation(
    invitation_id: str,
    candidate: Candidate = Depends(get_current_candidate),
):
    """Accept a sourcing invitation → create a deduplicated application for the job."""
    async with _get_session_factory()() as session:
        async with session.begin():
            inv_repo = SourcingInvitationRepository(session)
            inv = await inv_repo.get_for_candidate(
                invitation_id=invitation_id, candidate_id=candidate.id
            )
            if not inv:
                raise HTTPException(status_code=404, detail="Invitation not found")
            if inv["status"] != "pending":
                raise HTTPException(status_code=409, detail="Invitation already responded to")

            job_id = str(inv["job_id"])
            company_id = str(inv["company_id"])
            await session.execute(
                sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                {"cid": company_id},
            )
            job_title = (
                await session.execute(
                    sa.text("SELECT title FROM jobs WHERE id = :id"), {"id": job_id}
                )
            ).scalar_one_or_none() or ""

            response = await _apply_with_stored_cv(
                session,
                candidate=candidate,
                job_id=job_id,
                company_id=company_id,
                job_title=str(job_title),
                source="sourcing_invitation",
            )
            await inv_repo.set_status(invitation_id=invitation_id, status="accepted")

    asyncio.create_task(
        run_screening_background(
            application_id=response.id,
            company_id=company_id,
            job_id=job_id,
            job_title=response.job_title or "",
            candidate_email=candidate.email,
        )
    )
    return response
