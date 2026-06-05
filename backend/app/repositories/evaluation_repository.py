from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import Evaluation


class EvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        application_id: str,
        company_id: str,
        overall_score: int,
        recommendation: str,
        dimension_scores: list[Any],
        consistency_flags: list[Any],
        communication_quality: dict[str, Any],
        confidence_flag: bool,
        confidence_reason: str | None,
        summary: str | None,
    ) -> Evaluation:
        ev = Evaluation(
            id=str(uuid.uuid4()),
            application_id=application_id,
            company_id=company_id,
            overall_score=overall_score,
            recommendation=recommendation,
            dimension_scores=dimension_scores,
            consistency_flags=consistency_flags,
            communication_quality=communication_quality,
            confidence_flag=confidence_flag,
            confidence_reason=confidence_reason,
            summary=summary,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(ev)
        await self._session.flush()
        return ev

    async def get_by_id(self, evaluation_id: str) -> Evaluation | None:
        result = await self._session.execute(
            sa.select(Evaluation).where(Evaluation.id == evaluation_id)
        )
        return result.scalar_one_or_none()

    async def get_by_application_id(self, application_id: str) -> Evaluation | None:
        result = await self._session.execute(
            sa.select(Evaluation).where(Evaluation.application_id == application_id)
        )
        return result.scalar_one_or_none()

    async def list_by_job_ranked(self, job_id: str) -> list[dict[str, Any]]:
        """Return ranked shortlist for a job joined with candidate name."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT
                    e.id            AS evaluation_id,
                    e.application_id,
                    c.full_name,
                    e.overall_score,
                    e.recommendation,
                    e.confidence_flag,
                    e.created_at
                FROM evaluations e
                JOIN applications a ON a.id = e.application_id
                JOIN candidates c   ON c.id = a.candidate_id
                WHERE a.job_id = :job_id
                ORDER BY e.overall_score DESC
                """
            ),
            {"job_id": job_id},
        )
        return [dict(r) for r in result.mappings().all()]

    async def get_by_feedback_token(self, token: str) -> Evaluation | None:
        """Bypasses RLS — token is the authenticator for public candidate access."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT * FROM evaluations
                WHERE feedback_token = :token
                  AND feedback_token_expires_at > now()
                LIMIT 1
                """
            ),
            {"token": token},
        )
        row = result.mappings().first()
        if not row:
            return None
        ev = Evaluation.__new__(Evaluation)
        for k, v in row.items():
            object.__setattr__(ev, k, v)
        return ev

    async def set_feedback_token(
        self,
        evaluation_id: str,
        token: str,
        expires_at: datetime,
    ) -> None:
        await self._session.execute(
            sa.update(Evaluation)
            .where(Evaluation.id == evaluation_id)
            .values(
                feedback_token=token,
                feedback_token_expires_at=expires_at,
                updated_at=datetime.now(timezone.utc),
            )
        )
