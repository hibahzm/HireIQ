from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_authed_session, require_admin, require_recruiter_or_admin
from app.models.application import Application
from app.models.job import Job as JobModel
from app.models.user import User
from app.repositories.job_repository import JobRepository
from app.repositories.setup_conversation_repository import SetupConversationRepository
from app.schemas.jobs import (
    CreateJobRequest,
    JobCriteriaRequest,
    JobResponse,
    SetupConversationResponse,
    SetupTurnRequest,
    SetupTurnResponse,
)
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
        streaming_interview=body.streaming_interview,
        created_by=current_user.id,
    )
    return JobResponse(**job.__dict__)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    job = await JobRepository(session).get_by_id(job_id, current_user.company_id)
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
        .values(
            title=body.title,
            description=body.description,
            streaming_interview=body.streaming_interview,
            updated_at=datetime.now(timezone.utc),
        )
    )
    job = await JobRepository(session).get_by_id(job_id, current_user.company_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job.__dict__)


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    job = await JobRepository(session).get_by_id(job_id, current_user.company_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await session.execute(
        sa.select(Application.id)
        .where(Application.job_id == job_id)
        .limit(1)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete a job with applications. "
                "Close or archive it to preserve hiring history."
            ),
        )

    await session.execute(sa.delete(JobModel).where(JobModel.id == job_id))


@router.get("/{job_id}/setup/conversation", response_model=SetupConversationResponse)
async def get_setup_conversation(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    """Return the persisted setup chat so an interrupted setup resumes where it stopped."""
    job = await JobRepository(session).get_by_id(job_id, current_user.company_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    conv = await SetupConversationRepository(session).get_by_job_id(job_id)

    from app.models.job_criteria import JobCriteria

    criteria_row = (
        await session.execute(sa.select(JobCriteria).where(JobCriteria.job_id == job_id))
    ).scalar_one_or_none()
    criteria = None
    if criteria_row:
        criteria = {
            "required_skills": criteria_row.required_skills,
            "optional_skills": criteria_row.optional_skills,
            "experience_level": criteria_row.experience_level,
            "min_years_experience": criteria_row.min_years_experience,
            "evaluation_dimensions": criteria_row.evaluation_dimensions,
            "dealbreakers": criteria_row.dealbreakers,
            "min_screening_score": criteria_row.min_screening_score,
        }

    return SetupConversationResponse(
        messages=list(conv.messages) if conv else [],
        status=conv.status if conv else "in_progress",
        job_status=job.status,
        criteria=criteria,
    )


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


@router.put("/{job_id}/criteria", response_model=JobResponse)
async def save_manual_criteria(
    job_id: str,
    body: JobCriteriaRequest,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    try:
        job = await JobService(session).save_manual_criteria(
            job_id=job_id,
            company_id=current_user.company_id,
            actor_id=current_user.id,
            criteria=body.model_dump(),
        )
    except JobServiceError as exc:
        code = 404 if "not_found" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc))
    return JobResponse(**job.__dict__)


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


@router.post("/{job_id}/close", response_model=JobResponse)
async def close_job(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    try:
        job = await JobService(session).close_job(
            job_id=job_id,
            company_id=current_user.company_id,
            actor_id=current_user.id,
        )
    except JobServiceError as exc:
        code = 404 if "not_found" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc))
    return JobResponse(**job.__dict__)


@router.post("/{job_id}/reopen", response_model=JobResponse)
async def reopen_job(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    try:
        job = await JobService(session).reopen_job(
            job_id=job_id,
            company_id=current_user.company_id,
            actor_id=current_user.id,
        )
    except JobServiceError as exc:
        code = 404 if "not_found" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc))
    return JobResponse(**job.__dict__)


@router.post("/{job_id}/archive", response_model=JobResponse)
async def archive_job(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    try:
        job = await JobService(session).archive_job(
            job_id=job_id,
            company_id=current_user.company_id,
            actor_id=current_user.id,
        )
    except JobServiceError as exc:
        code = 404 if "not_found" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc))
    return JobResponse(**job.__dict__)
