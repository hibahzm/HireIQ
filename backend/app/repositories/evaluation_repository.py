from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._session.add(ev)
        await self._session.flush()
        return ev

    async def get_by_id(
        self, evaluation_id: str, company_id: str | None = None
    ) -> Evaluation | None:
        # company_id: explicit tenant scoping in addition to RLS (a privileged
        # DB role silently bypasses RLS policies).
        q = sa.select(Evaluation).where(Evaluation.id == evaluation_id)
        if company_id:
            q = q.where(Evaluation.company_id == company_id)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    async def get_by_application_id(self, application_id: str) -> Evaluation | None:
        result = await self._session.execute(
            sa.select(Evaluation).where(Evaluation.application_id == application_id)
        )
        return result.scalar_one_or_none()

    async def list_by_job_ranked(
        self, job_id: str, company_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return ranked shortlist for a job joined with candidate name."""
        company_clause = "AND e.company_id = :cid" if company_id else ""
        params: dict[str, Any] = {"job_id": job_id}
        if company_id:
            params["cid"] = str(company_id)
        result = await self._session.execute(
            sa.text(
                f"""
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
                WHERE a.job_id = :job_id {company_clause}
                ORDER BY e.overall_score DESC
                """
            ),
            params,
        )
        return [dict(r) for r in result.mappings().all()]

    async def _resolve_feedback_token(self, token: str) -> dict[str, Any] | None:
        """
        Token → evaluation row via the SECURITY DEFINER resolver (migration 0017):
        the candidate has no auth/company context, so a direct SELECT is empty
        under FORCE RLS. Also sets the RLS context for the resolved company so
        follow-up queries (job title) are properly scoped. Returns the row
        without the expiry filter — callers decide between 404 and 410.
        """
        import uuid as uuid_module

        try:
            uuid_module.UUID(token)
        except ValueError:
            return None
        result = await self._session.execute(
            sa.text("SELECT * FROM resolve_feedback_token(:token)"),
            {"token": token},
        )
        row = result.mappings().first()
        if not row:
            return None
        resolved = dict(row)
        await self._session.execute(
            sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
            {"cid": str(resolved["company_id"])},
        )
        return resolved

    async def get_by_feedback_token(self, token: str) -> Evaluation | None:
        """Public candidate access — the token is the authenticator. Expired → None."""
        from datetime import datetime

        row = await self._resolve_feedback_token(token)
        if not row:
            return None
        expires_at = row.get("feedback_token_expires_at")
        if not expires_at or expires_at <= datetime.now(UTC):
            return None
        return Evaluation(**row)

    async def get_feedback_token_row(self, token: str) -> dict[str, Any] | None:
        """Lookup by token *without* the expiry filter — used to distinguish an
        unknown token (404) from an expired one (410)."""
        return await self._resolve_feedback_token(token)

    async def get_job_title_by_application_id(self, application_id: str) -> str | None:
        """Resolve the job title for a feedback report. Bypasses RLS (public)."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT j.title
                FROM jobs j
                JOIN applications a ON a.job_id = j.id
                WHERE a.id = :application_id
                LIMIT 1
                """
            ),
            {"application_id": application_id},
        )
        row = result.mappings().first()
        return row["title"] if row else None

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
                updated_at=datetime.now(UTC),
            )
        )
