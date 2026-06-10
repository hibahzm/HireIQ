from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_authed_session, require_recruiter_or_admin
from app.db import _get_session_factory
from app.models.user import User
from app.redis_client import get_redis
from app.repositories.application_repository import ApplicationRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.candidate_repository import CandidateRepository
from app.schemas.applications import ApplicationResponse
from app.services.notification_service import NotificationService
from app.services.ocr_service import OcrService, OcrValidationError
from app.services.screening_service import run_screening_background
from app.services.storage_service import StorageService

logger = structlog.get_logger()

router = APIRouter(tags=["applications"])

MAX_CV_SIZE = 10 * 1024 * 1024  # 10 MB
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 3600  # 1 hour

# Accepted CV content types (V2-1: PDF + DOCX + JPG/PNG). Mapped to a blob extension.
ACCEPTED_CV_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
UNSUPPORTED_CV_MESSAGE = "Unsupported file type. Accepted: PDF, DOCX, JPG, PNG."


@router.post("/jobs/{job_id}/applications", response_model=ApplicationResponse, status_code=201)
async def submit_application(
    request: Request,
    job_id: str,
    full_name: str = Form(...),
    email: str = Form(...),
    cv_file: UploadFile = File(...),
    redis_client: Redis = Depends(get_redis),
):
    """Public — no auth. Rate-limited 5/IP/hr."""
    if cv_file.content_type not in ACCEPTED_CV_TYPES:
        raise HTTPException(status_code=422, detail=UNSUPPORTED_CV_MESSAGE)

    cv_bytes = await cv_file.read()
    if len(cv_bytes) > MAX_CV_SIZE:
        raise HTTPException(status_code=413, detail="CV file exceeds 10 MB limit")

    # Rate limit
    ip = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
    rate_key = f"ratelimit:cv:{ip_hash}"
    current = await redis_client.incr(rate_key)
    if current == 1:
        await redis_client.expire(rate_key, RATE_LIMIT_WINDOW)
    if current > RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many submissions. Try again later.")

    # Validate CV before touching the DB — dispatch on the declared type, and let the
    # extractor reject files whose bytes don't parse as the claimed type (renamed/corrupt).
    try:
        _, _ = await OcrService().extract(
            cv_bytes, filename=cv_file.filename or "cv", content_type=cv_file.content_type
        )
    except OcrValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid CV: {exc}")

    async with _get_session_factory()() as session:
        async with session.begin():
            # 1. Read the job WITHOUT RLS (uses the public_read_active_jobs policy from 0006)
            result = await session.execute(
                sa.text(
                    "SELECT id, company_id, title, status FROM jobs "
                    "WHERE id = :id AND status = 'active'"
                ),
                {"id": job_id},
            )
            job_row = result.mappings().first()
            if not job_row:
                raise HTTPException(
                    status_code=404, detail="Job not found or not accepting applications"
                )

            # 2. Now set RLS context — all subsequent queries are scoped to this company
            company_id = str(job_row["company_id"])
            await session.execute(
                sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                {"cid": company_id},
            )

            # 3. Duplicate check
            app_repo = ApplicationRepository(session)
            if await app_repo.get_by_job_and_email(job_id, email):
                raise HTTPException(
                    status_code=409, detail="Application already submitted for this job"
                )

            # 4. Store CV (preserve the original format's extension)
            blob_ext = ACCEPTED_CV_TYPES[cv_file.content_type]
            blob_key = f"cvs/{job_id}/{uuid.uuid4()}{blob_ext}"
            await StorageService().upload(blob_key, cv_bytes)

            # 5. Create candidate + application
            candidate = await CandidateRepository(session).get_or_create(
                email=email, full_name=full_name
            )
            application = await app_repo.create(
                job_id=job_id,
                candidate_id=candidate.id,
                company_id=company_id,
                cv_blob_key=blob_key,
            )

            await AuditLogRepository(session).log_event(
                event_type="application.created",
                actor_type="candidate",
                entity_type="application",
                entity_id=application.id,
                company_id=company_id,
            )

            response_data = ApplicationResponse(**application.__dict__)

    # 6. Fire-and-forget screening (owns its own session)
    asyncio.create_task(
        run_screening_background(
            application_id=application.id,
            company_id=company_id,
            job_id=job_id,
            job_title=str(job_row["title"]),
            candidate_email=email,
        )
    )

    return response_data


@router.get("/jobs/{job_id}/applications", response_model=list[ApplicationResponse])
async def list_applications(
    job_id: str,
    status: str | None = None,
    page: int = 1,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    apps = await ApplicationRepository(session).list_by_job(
        job_id, status_filter=status, page=page
    )
    return [ApplicationResponse(**a.__dict__) for a in apps]


@router.get("/applications/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    app = await ApplicationRepository(session).get_by_id(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationResponse(**app.__dict__)


@router.post("/applications/{application_id}/invite", status_code=200)
async def invite_to_interview(
    application_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
    redis_client: Redis = Depends(get_redis),
):
    repo = ApplicationRepository(session)
    app = await repo.get_by_id(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.screening_status != "qualified":
        raise HTTPException(status_code=422, detail="Can only invite qualified candidates")

    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await repo.set_interview_token(application_id, token, expires_at)

    await AuditLogRepository(session).log_event(
        event_type="application.interview_invited",
        actor_type="user",
        actor_id=current_user.id,
        entity_type="application",
        entity_id=application_id,
        company_id=current_user.company_id,
    )

    # Fetch candidate email for the notification
    result = await session.execute(
        sa.text(
            "SELECT c.email FROM candidates c "
            "JOIN applications a ON a.candidate_id = c.id "
            "WHERE a.id = :app_id"
        ),
        {"app_id": application_id},
    )
    candidate_email = result.scalar_one_or_none() or ""

    from app.config import get_settings

    await NotificationService(redis_client).send_invitation_email(
        candidate_email=candidate_email,
        interview_link=f"{get_settings().FRONTEND_ORIGIN}/interview/{token}",
    )

    return {"interview_token": token, "expires_at": expires_at.isoformat()}


@router.post("/applications/{application_id}/rescreen", status_code=202)
async def rescreen_application(
    application_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    """Re-run the screening pipeline for an application stuck before it completed."""
    repo = ApplicationRepository(session)
    app = await repo.get_by_id(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.screening_status not in ("pending", "failed"):
        raise HTTPException(
            status_code=422,
            detail="Only applications stuck in pending or failed screening can be re-run.",
        )

    row = (
        await session.execute(
            sa.text(
                "SELECT j.title AS job_title, c.email AS candidate_email "
                "FROM applications a "
                "JOIN jobs j ON j.id = a.job_id "
                "JOIN candidates c ON c.id = a.candidate_id "
                "WHERE a.id = :id"
            ),
            {"id": application_id},
        )
    ).mappings().first()

    # Reset to pending so the UI shows an in-flight re-run immediately.
    await repo.update_screening_status(application_id, "pending")

    await AuditLogRepository(session).log_event(
        event_type="application.rescreen_triggered",
        actor_type="user",
        actor_id=current_user.id,
        entity_type="application",
        entity_id=application_id,
        company_id=current_user.company_id,
    )

    asyncio.create_task(
        run_screening_background(
            application_id=application_id,
            company_id=str(current_user.company_id),
            job_id=str(app.job_id),
            job_title=str(row["job_title"]) if row else "the position",
            candidate_email=str(row["candidate_email"]) if row else "",
        )
    )

    return {"status": "rescreening", "application_id": application_id}
