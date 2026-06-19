from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
from app.services.notification_service import NotificationService
from app.services.sourcing_service import search_candidates_for_job, skill_names

router = APIRouter(prefix="/jobs", tags=["sourcing"])

# Only strong matches are auto-invited, so candidates aren't spammed with weak fits.
AUTO_INVITE_MIN_SCORE = 0.35


class SourcingInviteResult(BaseModel):
    invited: int  # new invitations sent this run
    skipped: int  # strong matches already invited / already applied


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


@router.post("/{job_id}/sourcing/invite", response_model=SourcingInviteResult)
async def invite_matches(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
    redis_client: Redis = Depends(get_redis),
):
    """Find strong matches for this job and invite them directly — no per-candidate
    review by the company. Candidates decide whether to apply from their portal;
    the company sees full details only once a candidate applies. Re-runnable: it
    skips anyone already invited or already applied.
    """
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
    # Strong matches only, and never re-invite someone who already applied.
    strong = [
        r
        for r in results
        if r["match_score"] >= AUTO_INVITE_MIN_SCORE and not r["already_applied"]
    ]

    company_name = (
        await session.execute(
            sa.text("SELECT name FROM companies WHERE id = :id"),
            {"id": current_user.company_id},
        )
    ).scalar_one_or_none() or "A company"
    link = f"{get_settings().FRONTEND_ORIGIN}/candidate"

    inv_repo = SourcingInvitationRepository(session)
    cand_repo = CandidateRepository(session)
    notifier = NotificationService(redis_client)

    invited = 0
    skipped = 0
    for r in strong:
        invitation_id = await inv_repo.create(
            job_id=job_id,
            candidate_id=r["candidate_id"],
            company_id=current_user.company_id,
        )
        if not invitation_id:
            skipped += 1  # already invited
            continue
        invited += 1
        candidate = await cand_repo.get_by_id(r["candidate_id"])
        if candidate:
            await notifier.send_sourcing_invitation_email(
                candidate.email, str(company_name), job.title, link
            )

    await AuditLogRepository(session).log_event(
        event_type="sourcing.invitations_sent",
        actor_type="user",
        actor_id=current_user.id,
        entity_type="job",
        entity_id=job_id,
        company_id=current_user.company_id,
        metadata={"invited": invited, "skipped": skipped},
    )
    return SourcingInviteResult(invited=invited, skipped=skipped)
