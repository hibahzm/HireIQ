from __future__ import annotations

import structlog
from fastapi.encoders import jsonable_encoder
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.job import Job
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.job_repository import JobRepository
from app.repositories.setup_conversation_repository import SetupConversationRepository

logger = structlog.get_logger()


class JobServiceError(Exception):
    pass


class JobService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = get_settings()

    async def create_job(
        self, *, company_id: str, title: str, created_by: str, description: str | None = None
    ) -> Job:
        repo = JobRepository(self._session)
        job = await repo.create(
            company_id=company_id, title=title, created_by=created_by, description=description
        )

        audit = AuditLogRepository(self._session)
        await audit.log_event(
            event_type="job.created",
            actor_type="user",
            actor_id=created_by,
            entity_type="job",
            entity_id=job.id,
            company_id=company_id,
        )
        return job

    async def advance_setup(
        self,
        *,
        job_id: str,
        company_id: str,
        user_message: str,
        actor_id: str,
    ) -> dict:
        job_repo = JobRepository(self._session)
        job = await job_repo.get_by_id(job_id)
        if not job:
            raise JobServiceError("job_not_found")
        if job.status not in ("draft", "setup", "setup_failed"):
            raise JobServiceError("invalid_job_status")

        # Transition into setup while the agent is actively collecting criteria.
        if job.status in ("draft", "setup_failed"):
            await job_repo.update_status(job_id, "setup")

        conv_repo = SetupConversationRepository(self._session)
        conv = await conv_repo.get_or_create(job_id=job_id, company_id=company_id)

        # On the very first turn, seed the agent with the recruiter-provided job
        # description (if any) so it can pre-extract criteria and only ask about
        # genuine gaps, instead of interrogating from scratch.
        effective_user_message = user_message
        if not conv.messages and not user_message and job.description:
            effective_user_message = (
                "Here is the job description for this role. Extract as much hiring "
                "criteria as you can from it, and only ask me about details that are "
                f"genuinely missing or ambiguous:\n\n{job.description}"
            )

        payload = jsonable_encoder({
            "job_id": job_id,
            "company_id": company_id,
            "conversation_history": list(conv.messages),
            "user_message": effective_user_message,
        })
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._settings.AGENTS_BASE_URL}/agents/job-setup/turn",
                    json=payload,
                    headers={"X-Internal-Secret": self._settings.AGENTS_INTERNAL_SECRET},
                )
                resp.raise_for_status()
        except Exception as exc:
            message = (
                "The setup assistant is unavailable right now. "
                "You can retry setup or enter criteria manually."
            )
            await job_repo.update_status(job_id, "setup_failed")
            await conv_repo.fail(conv.id, message)
            await AuditLogRepository(self._session).log_event(
                event_type="job.setup_failed",
                actor_type="system",
                entity_type="job",
                entity_id=job_id,
                company_id=company_id,
                metadata={"error": str(exc)[:500]},
            )
            return {"message": message, "status": "failed", "criteria_draft": None}

        agent_response = resp.json()

        # Persist messages (skip empty kickoff turns so history stays clean)
        if effective_user_message:
            await conv_repo.append_message(conv.id, "user", effective_user_message)
        await conv_repo.append_message(conv.id, "assistant", agent_response["message"])

        if agent_response["status"] == "completed":
            await conv_repo.complete(conv.id)
            criteria = agent_response.get("criteria_draft")
            if criteria:
                await self._upsert_criteria(job_id, company_id, criteria)

        return agent_response

    async def _upsert_criteria(self, job_id: str, company_id: str, criteria: dict) -> None:
        """Persist the agent's extracted criteria into job_criteria so the job can activate."""
        import sqlalchemy as sa

        from app.models.job_criteria import JobCriteria

        fields = dict(
            required_skills=criteria.get("required_skills", []),
            optional_skills=criteria.get("optional_skills", []),
            experience_level=criteria.get("experience_level") or "mid",
            min_years_experience=criteria.get("min_years_experience"),
            evaluation_dimensions=criteria.get("evaluation_dimensions", []),
            dealbreakers=criteria.get("dealbreakers", []),
            min_screening_score=criteria.get("min_screening_score", 60),
        )
        existing = (
            await self._session.execute(
                sa.select(JobCriteria).where(JobCriteria.job_id == job_id)
            )
        ).scalar_one_or_none()
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
        else:
            self._session.add(JobCriteria(job_id=job_id, company_id=company_id, **fields))
        await self._session.flush()

    async def activate_job(self, *, job_id: str, company_id: str, actor_id: str) -> Job:
        job_repo = JobRepository(self._session)
        job = await job_repo.get_by_id(job_id)
        if not job:
            raise JobServiceError("job_not_found")
        if job.status not in ("setup", "setup_failed", "closed"):
            raise JobServiceError("job_must_be_in_setup_status")

        # Verify criteria exist
        from app.models.job_criteria import JobCriteria
        import sqlalchemy as sa
        result = await self._session.execute(
            sa.select(JobCriteria).where(JobCriteria.job_id == job_id)
        )
        if not result.scalar_one_or_none():
            raise JobServiceError("criteria_not_set")

        job = await job_repo.update_status(job_id, "active")

        audit = AuditLogRepository(self._session)
        await audit.log_event(
            event_type="job.activated",
            actor_type="user",
            actor_id=actor_id,
            entity_type="job",
            entity_id=job_id,
            company_id=company_id,
        )
        return job

    async def save_manual_criteria(
        self,
        *,
        job_id: str,
        company_id: str,
        actor_id: str,
        criteria: dict,
    ) -> Job:
        job_repo = JobRepository(self._session)
        job = await job_repo.get_by_id(job_id)
        if not job:
            raise JobServiceError("job_not_found")
        if job.status not in ("draft", "setup", "setup_failed", "closed"):
            raise JobServiceError("invalid_job_status")

        await job_repo.upsert_criteria(job_id=job_id, company_id=company_id, criteria=criteria)
        job = await job_repo.update_status(job_id, "setup")
        await AuditLogRepository(self._session).log_event(
            event_type="job.criteria_manual_saved",
            actor_type="user",
            actor_id=actor_id,
            entity_type="job",
            entity_id=job_id,
            company_id=company_id,
        )
        return job

    async def close_job(self, *, job_id: str, company_id: str, actor_id: str) -> Job:
        return await self._transition_job(
            job_id=job_id,
            company_id=company_id,
            actor_id=actor_id,
            target_status="closed",
            event_type="job.closed",
            allowed_statuses=("active", "draft", "setup", "setup_failed"),
        )

    async def reopen_job(self, *, job_id: str, company_id: str, actor_id: str) -> Job:
        job = await self._transition_job(
            job_id=job_id,
            company_id=company_id,
            actor_id=actor_id,
            target_status="active",
            event_type="job.reopened",
            allowed_statuses=("closed",),
        )
        return job

    async def archive_job(self, *, job_id: str, company_id: str, actor_id: str) -> Job:
        return await self._transition_job(
            job_id=job_id,
            company_id=company_id,
            actor_id=actor_id,
            target_status="archived",
            event_type="job.archived",
            allowed_statuses=("draft", "setup", "setup_failed", "closed"),
        )

    async def _transition_job(
        self,
        *,
        job_id: str,
        company_id: str,
        actor_id: str,
        target_status: str,
        event_type: str,
        allowed_statuses: tuple[str, ...],
    ) -> Job:
        job_repo = JobRepository(self._session)
        job = await job_repo.get_by_id(job_id)
        if not job:
            raise JobServiceError("job_not_found")
        if job.status not in allowed_statuses:
            raise JobServiceError(f"cannot_transition_from_{job.status}")

        updated = await job_repo.update_status(job_id, target_status)
        await AuditLogRepository(self._session).log_event(
            event_type=event_type,
            actor_type="user",
            actor_id=actor_id,
            entity_type="job",
            entity_id=job_id,
            company_id=company_id,
        )
        return updated
