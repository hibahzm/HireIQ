from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.repositories.application_repository import ApplicationRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.interview_repository import (
    InterviewMessageRepository,
)
from app.services.usage_service import record_usage_events

logger = structlog.get_logger()


class EvaluationService:
    def __init__(self, session: AsyncSession, redis=None) -> None:
        self._session = session
        self._redis = redis
        self._settings = get_settings()

    # ------------------------------------------------------------------ T077
    async def generate_feedback_token(self, evaluation_id: str) -> str:
        """Mint a UUID feedback token with 30-day expiry and persist it."""
        token = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(days=30)
        repo = EvaluationRepository(self._session)
        await repo.set_feedback_token(evaluation_id, token, expires_at)
        return token

    # ------------------------------------------------------------------ T073
    async def evaluate_from_session(self, *, session_id: str, company_id: str) -> None:
        """Triggered by InterviewService on session_complete."""
        log = logger.bind(session_id=session_id, company_id=company_id)
        log.info("evaluation.started")

        msg_repo = InterviewMessageRepository(self._session)
        app_repo = ApplicationRepository(self._session)
        eval_repo = EvaluationRepository(self._session)
        audit = AuditLogRepository(self._session)

        # 1. Load interview session
        import sqlalchemy as sa

        from app.models.interview_session import InterviewSession

        result = await self._session.execute(
            sa.select(InterviewSession).where(InterviewSession.id == session_id)
        )
        interview_session = result.scalar_one_or_none()
        if not interview_session:
            log.error("evaluation.session_not_found")
            return

        application_id = interview_session.application_id

        # 2. Load application + candidate + job criteria
        from app.models.application import Application
        from app.models.candidate import Candidate
        from app.models.job_criteria import JobCriteria

        result = await self._session.execute(
            sa.select(Application).where(Application.id == application_id)
        )
        application = result.scalar_one_or_none()
        if not application:
            log.error("evaluation.application_not_found")
            return

        result = await self._session.execute(
            sa.select(Candidate).where(Candidate.id == application.candidate_id)
        )
        candidate = result.scalar_one_or_none()

        result = await self._session.execute(
            sa.select(JobCriteria).where(JobCriteria.job_id == application.job_id)
        )
        criteria_model = result.scalar_one_or_none()
        if not criteria_model:
            log.error("evaluation.criteria_not_found", job_id=application.job_id)
            return

        job_criteria: dict[str, Any] = {
            "required_skills": criteria_model.required_skills,
            "optional_skills": criteria_model.optional_skills,
            "experience_level": criteria_model.experience_level,
            "min_years_experience": criteria_model.min_years_experience,
            "evaluation_dimensions": criteria_model.evaluation_dimensions,
            "dealbreakers": criteria_model.dealbreakers,
            "min_screening_score": criteria_model.min_screening_score,
        }

        cv_text = application.cv_text or ""

        # 3. Build transcript from interview messages
        messages = await msg_repo.list_by_session(session_id)
        transcript = [
            {
                "turn_index": m.turn_index,
                "speaker": m.speaker,
                "content_text": m.content_text if not m.is_blocked else "[blocked]",
            }
            for m in messages
        ]

        # 4. Call agents /evaluate
        payload = jsonable_encoder(
            {
                "application_id": application_id,
                "company_id": company_id,
                "cv_text": cv_text,
                "job_criteria": job_criteria,
                "transcript": transcript,
            }
        )
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    f"{self._settings.AGENTS_BASE_URL}/agents/evaluate",
                    json=payload,
                    headers={"X-Internal-Secret": self._settings.AGENTS_INTERNAL_SECRET},
                )
                resp.raise_for_status()
            agent_result = resp.json()
        except Exception as exc:
            log.error("evaluation.agent_call_failed", error=str(exc))
            await audit.log_event(
                company_id=company_id,
                actor_type="system",
                actor_id=session_id,
                event_type="evaluation.failed",
                entity_type="application",
                entity_id=application_id,
                metadata={"error": str(exc)},
            )
            return
        await record_usage_events(
            self._session,
            company_id=company_id,
            events=agent_result.get("usage_events"),
            metadata={"application_id": application_id, "session_id": session_id},
        )

        # 5. Parse summary
        feedback_summary = agent_result.get("feedback_summary") or {}
        strengths = feedback_summary.get("strengths", "")
        areas = feedback_summary.get("areas_for_improvement", "")
        summary_text = None
        if strengths or areas:
            summary_text = f"Strengths: {strengths}\nAreas for improvement: {areas}"

        # 6. Persist Evaluation
        evaluation = await eval_repo.create(
            application_id=application_id,
            company_id=company_id,
            overall_score=agent_result.get("overall_score", 0),
            recommendation=agent_result.get("recommendation", "uncertain"),
            dimension_scores=agent_result.get("dimension_scores", []),
            consistency_flags=agent_result.get("consistency_flags", []),
            communication_quality=agent_result.get("communication_quality", {}),
            confidence_flag=agent_result.get("confidence_flag", False),
            confidence_reason=agent_result.get("confidence_reason"),
            summary=summary_text,
        )

        # 7. Update application status to evaluated
        await app_repo.update_status(application_id, "evaluated")

        # 8. Generate feedback token (T077)
        feedback_token = await self.generate_feedback_token(evaluation.id)

        # 9. Notify the candidate — outcome-dependent. A "hire" recommendation gets a
        # positive "the team will be in touch" email; anything else gets the feedback
        # report with growth tips. Best-effort: email failure never fails evaluation.
        if candidate and candidate.email:
            from app.models.job import Job

            result = await self._session.execute(sa.select(Job).where(Job.id == application.job_id))
            job = result.scalar_one_or_none()
            job_title = job.title if job else "the position"
            feedback_url = f"{self._settings.FRONTEND_ORIGIN}/feedback/{feedback_token}"
            try:
                from app.services.notification_service import NotificationService

                notifier = NotificationService(self._redis)
                if evaluation.recommendation == "hire":
                    await notifier.send_interview_advance_email(
                        candidate_email=candidate.email,
                        job_title=job_title,
                    )
                else:
                    await notifier.send_feedback_email(
                        candidate_email=candidate.email,
                        job_title=job_title,
                        feedback_url=feedback_url,
                    )
            except Exception as exc:
                log.warning("evaluation.candidate_email_failed", error=str(exc))

        # 10. Audit log
        await audit.log_event(
            company_id=company_id,
            actor_type="system",
            actor_id=session_id,
            event_type="evaluation.completed",
            entity_type="evaluation",
            entity_id=evaluation.id,
            metadata={
                "overall_score": evaluation.overall_score,
                "recommendation": evaluation.recommendation,
                "confidence_flag": evaluation.confidence_flag,
            },
        )
        log.info(
            "evaluation.completed",
            evaluation_id=evaluation.id,
            overall_score=evaluation.overall_score,
        )
