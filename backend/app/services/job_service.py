from __future__ import annotations

import structlog
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

    async def create_job(self, *, company_id: str, title: str, created_by: str) -> Job:
        repo = JobRepository(self._session)
        job = await repo.create(company_id=company_id, title=title, created_by=created_by)

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
        if job.status not in ("draft", "setup"):
            raise JobServiceError("invalid_job_status")

        # Transition to setup if still in draft
        if job.status == "draft":
            await job_repo.update_status(job_id, "setup")

        conv_repo = SetupConversationRepository(self._session)
        conv = await conv_repo.get_or_create(job_id=job_id, company_id=company_id)

        # Call agents service
        import httpx

        payload = {
            "job_id": job_id,
            "company_id": company_id,
            "conversation_history": list(conv.messages),
            "user_message": user_message,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._settings.AGENTS_BASE_URL}/agents/job-setup/turn",
                json=payload,
                headers={"X-Internal-Secret": self._settings.AGENTS_INTERNAL_SECRET},
            )
            resp.raise_for_status()
        agent_response = resp.json()

        # Persist messages
        await conv_repo.append_message(conv.id, "user", user_message)
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
        if job.status != "setup":
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
