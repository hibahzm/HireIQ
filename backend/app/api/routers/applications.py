from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.api.deps import require_recruiter_or_admin
from app.db import get_db
from app.models.user import User
from app.redis_client import get_redis
from app.repositories.application_repository import ApplicationRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.job_repository import JobRepository
from app.schemas.applications import ApplicationResponse
from app.services.notification_service import NotificationService
from app.services.ocr_service import OcrService, OcrValidationError
from app.services.screening_service import run_screening_background
from app.services.storage_service import StorageService

logger = structlog.get_logger()

router = APIRouter(tags=["applications"])

MAX_CV_SIZE = 10 * 1024 * 1024  # 10 MB
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds


@router.post("/jobs/{job_id}/applications", response_model=ApplicationResponse, status_code=201)
async def submit_application(
    request: Request,
    job_id: str,
    full_name: str = Form(...),
    email: str = Form(...),
    cv_file: UploadFile = File(...),
    db=Depends(get_db),
    redis_dep=Depends(get_redis),
):
    """Public endpoint — no auth required. Rate-limited per IP."""
    # File type check (PDF only in MVP)
    if cv_file.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Only PDF files are accepted")

    # File size check
    cv_bytes = await cv_file.read()
    if len(cv_bytes) > MAX_CV_SIZE:
        raise HTTPException(status_code=413, detail="CV file exceeds 10 MB limit")

    # Rate limiting: 5 submissions per IP per hour
    async for r in redis_dep:
        ip = request.client.host if request.client else "unknown"
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
        rate_key = f"ratelimit:cv:{ip_hash}"
        current = await r.incr(rate_key)
        if current == 1:
            await r.expire(rate_key, RATE_LIMIT_WINDOW)
        if current > RATE_LIMIT_MAX:
            raise HTTPException(status_code=429, detail="Too many submissions. Try again later.")

    async for session in db:
        job_repo = JobRepository(session)
        job = await job_repo.get_by_id(job_id)
        if not job or job.status != "active":
            raise HTTPException(status_code=404, detail="Job not found or not accepting applications")

        app_repo = ApplicationRepository(session)
        # Duplicate check
        existing = await app_repo.get_by_job_and_email(job_id, email)
        if existing:
            raise HTTPException(status_code=409, detail="Application already submitted for this job")

        # Validate CV before creating any record (FR-010)
        ocr = OcrService()
        try:
            _, _ = await ocr.extract(cv_bytes)
        except OcrValidationError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid CV: {exc}")

        # Store CV
        blob_key = f"cvs/{job_id}/{uuid.uuid4()}.pdf"
        storage = StorageService()
        await storage.upload(blob_key, cv_bytes)

        # Create candidate + application records
        cand_repo = CandidateRepository(session)
        candidate = await cand_repo.get_or_create(email=email, full_name=full_name)
        application = await app_repo.create(
            job_id=job_id,
            candidate_id=candidate.id,
            company_id=job.company_id,
            cv_blob_key=blob_key,
        )

        audit = AuditLogRepository(session)
        await audit.log_event(
            event_type="application.created",
            actor_type="candidate",
            entity_type="application",
            entity_id=application.id,
            company_id=job.company_id,
        )

        # Kick off background screening — logic lives in ScreeningService (Principle III)
        asyncio.create_task(
            run_screening_background(
                application_id=application.id,
                company_id=job.company_id,
                job_id=job_id,
                job_title=job.title,
                candidate_email=email,
            )
        )

        return ApplicationResponse(**application.__dict__)


@router.get("/jobs/{job_id}/applications", response_model=list[ApplicationResponse])
async def list_applications(
    job_id: str,
    status: str | None = None,
    page: int = 1,
    current_user: User = Depends(require_recruiter_or_admin),
    db=Depends(get_db),
):
    async for session in db:
        repo = ApplicationRepository(session)
        apps = await repo.list_by_job(job_id, status_filter=status, page=page)
        return [ApplicationResponse(**a.__dict__) for a in apps]


@router.get("/applications/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    db=Depends(get_db),
):
    async for session in db:
        repo = ApplicationRepository(session)
        app = await repo.get_by_id(application_id)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        return ApplicationResponse(**app.__dict__)


@router.post("/applications/{application_id}/invite", status_code=200)
async def invite_to_interview(
    application_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    db=Depends(get_db),
    redis_dep=Depends(get_redis),
):
    async for session in db:
        async for r in redis_dep:
            repo = ApplicationRepository(session)
            app = await repo.get_by_id(application_id)
            if not app:
                raise HTTPException(status_code=404, detail="Application not found")
            if app.screening_status != "qualified":
                raise HTTPException(status_code=422, detail="Can only invite qualified candidates")

            token = str(uuid.uuid4())
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            await repo.set_interview_token(application_id, token, expires_at)

            audit = AuditLogRepository(session)
            await audit.log_event(
                event_type="application.interview_invited",
                actor_type="user",
                actor_id=current_user.id,
                entity_type="application",
                entity_id=application_id,
                company_id=current_user.company_id,
            )

            interview_link = f"/interview/{token}"
            notif = NotificationService(r)
            await notif.send_invitation_email(
                candidate_email="",  # would fetch from candidate record
                interview_link=interview_link,
            )
            return {"interview_token": token, "expires_at": expires_at.isoformat()}
