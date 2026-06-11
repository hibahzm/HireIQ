from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application


class ApplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        job_id: str,
        candidate_id: str,
        company_id: str,
        cv_blob_key: str,
    ) -> Application:
        app = Application(
            id=str(uuid.uuid4()),
            job_id=job_id,
            candidate_id=candidate_id,
            company_id=company_id,
            cv_blob_key=cv_blob_key,
            screening_status="pending",
            status="applied",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(app)
        await self._session.flush()
        return app

    async def get_by_id(self, application_id: str) -> Application | None:
        result = await self._session.execute(
            sa.select(Application).where(Application.id == application_id)
        )
        return result.scalar_one_or_none()

    async def get_by_job_and_email(self, job_id: str, email: str) -> Application | None:
        result = await self._session.execute(
            sa.text(
                """
                SELECT a.* FROM applications a
                JOIN candidates c ON c.id = a.candidate_id
                WHERE a.job_id = :job_id AND lower(c.email) = lower(:email)
                LIMIT 1
                """
            ),
            {"job_id": job_id, "email": email},
        )
        row = result.mappings().first()
        if not row:
            return None
        return Application(**dict(row))

    async def list_by_job(
        self,
        job_id: str,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Application]:
        q = sa.select(Application).where(Application.job_id == job_id)
        if status_filter:
            q = q.where(Application.screening_status == status_filter)
        q = q.order_by(Application.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def update_screening_result(
        self,
        application_id: str,
        *,
        cv_text: str,
        cv_extraction_method: str,
        screening_score: int,
        screening_rationale: str,
        screening_status: str,
        status: str,
    ) -> None:
        await self._session.execute(
            sa.update(Application)
            .where(Application.id == application_id)
            .values(
                cv_text=cv_text,
                cv_extraction_method=cv_extraction_method,
                screening_score=screening_score,
                screening_rationale=screening_rationale,
                screening_status=screening_status,
                status=status,
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def update_status(self, application_id: str, status: str) -> None:
        await self._session.execute(
            sa.update(Application)
            .where(Application.id == application_id)
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )

    async def update_screening_status(self, application_id: str, screening_status: str) -> None:
        await self._session.execute(
            sa.update(Application)
            .where(Application.id == application_id)
            .values(screening_status=screening_status, updated_at=datetime.now(timezone.utc))
        )

    async def update_screening_failure(self, application_id: str, reason: str) -> None:
        await self._session.execute(
            sa.update(Application)
            .where(Application.id == application_id)
            .values(
                screening_status="failed",
                screening_rationale=reason,
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def set_interview_token(
        self,
        application_id: str,
        token: str,
        expires_at: datetime,
    ) -> None:
        await self._session.execute(
            sa.update(Application)
            .where(Application.id == application_id)
            .values(
                interview_token=token,
                interview_token_expires_at=expires_at,
                status="invited",
                updated_at=datetime.now(timezone.utc),
            )
        )
