from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_authed_session, require_recruiter_or_admin
from app.config import get_settings
from app.models.job_criteria import JobCriteria
from app.models.user import User
from app.redis_client import get_redis
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.job_repository import JobRepository
from app.repositories.sourcing_invitation_repository import SourcingInvitationRepository
from app.schemas.candidates import InviteCandidateRequest, SourcingCandidate
from app.services.notification_service import NotificationService
from app.services.sourcing_service import search_candidates_for_job, skill_names

router = APIRouter(prefix="/jobs", tags=["sourcing"])


def _build_query_text(description: str | None, criteria: JobCriteria | None) -> str:
    parts: list[str] = []
    if description:
        parts.append(description)
    if criteria:
        parts.extend(skill_names(criteria.required_skills))
        parts.extend(skill_names(criteria.optional_skills))
        if criteria.experience_level:
            parts.append(criteria.experience_level)
    return " ".join(parts).strip()


async def _load_sourcing_job(session: AsyncSession, job_id: str, company_id: str):
    job = await JobRepository(session).get_by_id(job_id, company_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.sourcing_enabled:
        raise HTTPException(status_code=400, detail="In-app sourcing is not enabled for this job")
    return job


@router.get("/{job_id}/sourcing", response_model=list[SourcingCandidate])
async def search_sourcing(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    job = await _load_sourcing_job(session, job_id, current_user.company_id)
    criteria = (
        await session.execute(sa.select(JobCriteria).where(JobCriteria.job_id == job_id))
    ).scalar_one_or_none()
    query_text = _build_query_text(job.description, criteria)
    if not query_text:
        raise HTTPException(
            status_code=422,
            detail="Add a job description or criteria before sourcing candidates.",
        )

    results = await search_candidates_for_job(
        session,
        job_id=job_id,
        query_text=query_text,
        required_skills=(criteria.required_skills if criteria else []) or [],
        optional_skills=(criteria.optional_skills if criteria else []) or [],
        experience_level=criteria.experience_level if criteria else None,
    )
    return [SourcingCandidate(**r) for r in results]


@router.post("/{job_id}/sourcing/{candidate_id}/invite", status_code=201)
async def invite_candidate(
    job_id: str,
    candidate_id: str,
    body: InviteCandidateRequest | None = None,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
    redis_client: Redis = Depends(get_redis),
):
    job = await _load_sourcing_job(session, job_id, current_user.company_id)

    candidate = await CandidateRepository(session).get_by_id(candidate_id)
    if not candidate or not candidate.open_to_work:
        raise HTTPException(
            status_code=422, detail="Candidate is not available for sourcing invitations"
        )

    invitation_id = await SourcingInvitationRepository(session).create(
        job_id=job_id,
        candidate_id=candidate_id,
        company_id=current_user.company_id,
        message=body.message if body else None,
    )
    if not invitation_id:
        raise HTTPException(status_code=409, detail="Candidate already invited to this job")

    company_name = (
        await session.execute(
            sa.text("SELECT name FROM companies WHERE id = :id"),
            {"id": current_user.company_id},
        )
    ).scalar_one_or_none() or "A company"

    await AuditLogRepository(session).log_event(
        event_type="sourcing.invitation_sent",
        actor_type="user",
        actor_id=current_user.id,
        entity_type="sourcing_invitation",
        entity_id=invitation_id,
        company_id=current_user.company_id,
    )

    link = f"{get_settings().FRONTEND_ORIGIN}/candidate"
    await NotificationService(redis_client).send_sourcing_invitation_email(
        candidate.email, str(company_name), job.title, link
    )
    return {"id": invitation_id, "status": "pending"}
