from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.job_criteria import JobCriteria


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, company_id: str, title: str, created_by: str, description: str | None = None
    ) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            company_id=company_id,
            title=title,
            description=description,
            status="draft",
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def get_by_id(self, job_id: str) -> Job | None:
        result = await self._session.execute(
            sa.select(Job).where(Job.id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: str, status_filter: str | None = None) -> list[Job]:
        q = sa.select(Job).where(Job.company_id == company_id)
        if status_filter:
            q = q.where(Job.status == status_filter)
        result = await self._session.execute(q.order_by(Job.created_at.desc()))
        return list(result.scalars().all())

    async def update_status(self, job_id: str, status: str) -> Job | None:
        await self._session.execute(
            sa.update(Job)
            .where(Job.id == job_id)
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )
        return await self.get_by_id(job_id)

    async def upsert_criteria(self, *, job_id: str, company_id: str, criteria: dict) -> JobCriteria:
        existing = await self._session.execute(
            sa.select(JobCriteria).where(JobCriteria.job_id == job_id)
        )
        existing = existing.scalar_one_or_none()
        if existing:
            for key, value in criteria.items():
                setattr(existing, key, value)
            existing.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
            return existing

        jc = JobCriteria(
            id=str(uuid.uuid4()),
            job_id=job_id,
            company_id=company_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            **criteria,
        )
        self._session.add(jc)
        await self._session.flush()
        return jc
