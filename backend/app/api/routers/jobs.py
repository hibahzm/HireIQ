from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_authed_session, require_recruiter_or_admin
from app.models.application import Application
from app.models.job import Job as JobModel
from app.models.user import User
from app.repositories.job_repository import JobRepository
from app.schemas.jobs import CreateJobRequest, JobResponse, SetupTurnRequest, SetupTurnResponse
from app.services.job_service import JobService, JobServiceError

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: str | None = None,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    jobs = await JobRepository(session).list_by_company(
        current_user.company_id, status_filter=status
    )
    return [JobResponse(**j.__dict__) for j in jobs]


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: CreateJobRequest,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    job = await JobService(session).create_job(
        company_id=current_user.company_id,
        title=body.title,
        description=body.description,
        created_by=current_user.id,
    )
    return JobResponse(**job.__dict__)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    job = await JobRepository(session).get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job.__dict__)


@router.put("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: str,
    body: CreateJobRequest,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    await session.execute(
        sa.update(JobModel)
        .where(JobModel.id == job_id)
        .values(title=body.title, updated_at=datetime.now(timezone.utc))
    )
    job = await JobRepository(session).get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job.__dict__)


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    job = await JobRepository(session).get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    blocking_statuses = ("screening", "qualified", "invited", "interviewing")
    result = await session.execute(
        sa.select(Application.id)
        .where(Application.job_id == job_id)
        .where(Application.status.in_(blocking_statuses))
        .limit(1)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete a job with active applications. "
                "Close the job first, then delete once all applications are resolved."
            ),
        )

    await session.execute(sa.delete(JobModel).where(JobModel.id == job_id))


@router.post("/{job_id}/setup/turn", response_model=SetupTurnResponse)
async def job_setup_turn(
    job_id: str,
    body: SetupTurnRequest,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    try:
        result = await JobService(session).advance_setup(
            job_id=job_id,
            company_id=current_user.company_id,
            user_message=body.user_message,
            actor_id=current_user.id,
        )
    except JobServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SetupTurnResponse(**result)


@router.post("/{job_id}/activate", response_model=JobResponse)
async def activate_job(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    try:
        job = await JobService(session).activate_job(
            job_id=job_id,
            company_id=current_user.company_id,
            actor_id=current_user.id,
        )
    except JobServiceError as exc:
        code = 404 if "not_found" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc))
    return JobResponse(**job.__dict__)
