from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.repositories.application_repository import ApplicationRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.services.notification_service import NotificationService
from app.services.ocr_service import OcrService, OcrValidationError
from app.services.storage_service import StorageService
from app.services.usage_service import record_usage_events

logger = structlog.get_logger()


async def run_screening_background(
    *,
    application_id: str,
    company_id: str,
    job_id: str,
    job_title: str,
    candidate_email: str,
) -> None:
    """
    Fire-and-forget screening pipeline. Creates its own DB session so it can
    run as an asyncio.Task without inheriting the request session. Owned here
    (not in the router) per Principle III.
    """
    from app.db import _get_session_factory
    from app.models.job_criteria import JobCriteria
    import sqlalchemy as sa

    try:
        async with _get_session_factory()() as session:
            async with session.begin():
                await session.execute(
                    sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                    {"cid": company_id},
                )
                result = await session.execute(
                    sa.select(JobCriteria).where(JobCriteria.job_id == job_id)
                )
                criteria_model = result.scalar_one_or_none()
                if not criteria_model:
                    reason = (
                        "Job criteria are missing. Complete job setup or save manual criteria, "
                        "then re-run screening."
                    )
                    logger.warning("screening.no_criteria", job_id=job_id)
                    await ApplicationRepository(session).update_screening_failure(
                        application_id, reason
                    )
                    await AuditLogRepository(session).log_event(
                        event_type="cv.screening.failed",
                        actor_type="system",
                        entity_type="application",
                        entity_id=application_id,
                        company_id=company_id,
                        metadata={"reason": "missing_job_criteria"},
                    )
                    return
                job_criteria = {
                    "required_skills": criteria_model.required_skills,
                    "optional_skills": criteria_model.optional_skills,
                    "experience_level": criteria_model.experience_level,
                    "evaluation_dimensions": criteria_model.evaluation_dimensions,
                    "dealbreakers": criteria_model.dealbreakers,
                    "min_screening_score": criteria_model.min_screening_score,
                }
                from app.models.job import Job
                job_desc_row = await session.execute(
                    sa.select(Job.description).where(Job.id == job_id)
                )
                job_description = job_desc_row.scalar_one_or_none() or ""
                svc = ScreeningService(session)
                await svc.screen(
                    application_id=application_id,
                    company_id=company_id,
                    job_title=job_title,
                    candidate_email=candidate_email,
                    job_criteria=job_criteria,
                    job_description=job_description,
                    job_id=job_id,
                )
    except Exception:
        # This runs as a fire-and-forget asyncio.Task; an unhandled error here
        # rolls back the transaction and leaves the application stuck in
        # `pending` forever (and logs "Task exception was never retrieved").
        # Record the failure on its own session so the recruiter sees a terminal
        # state instead of an application that never resolves.
        logger.exception("screening.failed", application_id=application_id, job_id=job_id)
        try:
            async with _get_session_factory()() as session:
                async with session.begin():
                    await session.execute(
                        sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                        {"cid": company_id},
                    )
                    await ApplicationRepository(session).update_screening_failure(
                        application_id,
                        (
                            "Screening failed because the AI screening pipeline could not finish. "
                            "Check the backend and agent logs, then re-run screening."
                        ),
                    )
        except Exception:
            logger.exception("screening.failed_status_update", application_id=application_id)


class ScreeningService:
    def __init__(self, session: AsyncSession, redis=None) -> None:
        self._session = session
        self._settings = get_settings()
        self._storage = StorageService()
        self._ocr = OcrService()
        self._notification = NotificationService(redis)

    async def screen(
        self,
        *,
        application_id: str,
        company_id: str,
        job_title: str,
        candidate_email: str,
        job_criteria: dict,
        job_id: str,
        job_description: str = "",
    ) -> None:
        """Orchestrate: OCR → agents /cv-screen (full job description + full CV) → persist."""
        app_repo = ApplicationRepository(self._session)
        audit = AuditLogRepository(self._session)

        await audit.log_event(
            event_type="cv.screening.started",
            actor_type="system",
            entity_type="application",
            entity_id=application_id,
            company_id=company_id,
        )

        # 1. Download CV from storage
        application = await app_repo.get_by_id(application_id)
        if not application:
            return
        cv_bytes = await self._storage.download(application.cv_blob_key)

        # 2. OCR — pass the blob key as the filename so the extractor dispatches
        # on the real format; the default ("cv.pdf") made every DOCX/image CV
        # re-extract as a PDF here and fail screening with "corrupted_pdf".
        try:
            cv_text, extraction_method = await self._ocr.extract(
                cv_bytes, filename=application.cv_blob_key
            )
        except OcrValidationError as exc:
            reason = f"CV extraction failed: {exc}"
            logger.error("cv.ocr.failed", application_id=application_id, error=str(exc))
            await app_repo.update_screening_failure(application_id, reason)
            await audit.log_event(
                event_type="cv.screening.failed",
                actor_type="system",
                entity_type="application",
                entity_id=application_id,
                company_id=company_id,
                metadata={"reason": "ocr_failed", "error": str(exc)[:500]},
            )
            return

        # 3. Call agents /cv-screen with the full job description + full CV text.
        # (We deliberately do NOT chunk/embed/retrieve here: the screener reasons
        # over the complete CV against the complete job, which is both simpler and
        # avoids ever mixing one candidate's CV into another's screening context.)
        import httpx

        payload = jsonable_encoder({
            "application_id": application_id,
            "company_id": company_id,
            "cv_text": cv_text,
            "job_description": job_description,
            "job_criteria": job_criteria,
        })
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._settings.AGENTS_BASE_URL}/agents/cv-screen",
                json=payload,
                headers={"X-Internal-Secret": self._settings.AGENTS_INTERNAL_SECRET},
            )
            resp.raise_for_status()
        agent_result = resp.json()
        await record_usage_events(
            self._session,
            company_id=company_id,
            events=agent_result.get("usage_events"),
            metadata={"application_id": application_id, "job_id": job_id},
        )

        # 6. Persist results. Anything other than a clear qualified/rejected verdict
        # (e.g. an unparseable LLM response) is a re-runnable failure, not a rejection.
        agent_status = agent_result["status"]
        if agent_status not in ("qualified", "rejected"):
            reason = agent_result.get("rationale") or "Screening did not produce a verdict."
            await app_repo.update_screening_failure(application_id, reason)
            await audit.log_event(
                event_type="cv.screening.failed",
                actor_type="system",
                entity_type="application",
                entity_id=application_id,
                company_id=company_id,
                metadata={"reason": "no_verdict", "agent_status": agent_status},
            )
            return

        final_status = "qualified" if agent_status == "qualified" else "rejected"
        await app_repo.update_screening_result(
            application_id,
            cv_text=cv_text,
            cv_extraction_method=extraction_method,
            screening_score=agent_result["score"],
            screening_rationale=agent_result["rationale"],
            screening_status=agent_status,
            status=final_status,
        )

        await audit.log_event(
            event_type="cv.screening.completed",
            actor_type="system",
            entity_type="application",
            entity_id=application_id,
            company_id=company_id,
            metadata={"score": agent_result["score"], "status": agent_status},
        )

        # 7. Qualified candidates are invited to interview immediately — no manual
        # recruiter click. The invitation email carries the interview link (console
        # backend in dev, real email via Resend in prod). Others get a confirmation.
        if final_status == "qualified":
            await self._auto_invite(
                application_id=application_id,
                company_id=company_id,
                candidate_email=candidate_email,
            )
        else:
            await self._notification.send_rejection_email(
                candidate_email=candidate_email,
                job_title=job_title,
            )

    async def _auto_invite(
        self,
        *,
        application_id: str,
        company_id: str,
        candidate_email: str,
    ) -> None:
        app_repo = ApplicationRepository(self._session)
        token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=self._settings.INTERVIEW_LINK_EXPIRY_HOURS
        )
        await app_repo.set_interview_token(application_id, token, expires_at)

        await AuditLogRepository(self._session).log_event(
            event_type="application.interview_invited",
            actor_type="system",
            entity_type="application",
            entity_id=application_id,
            company_id=company_id,
            metadata={"trigger": "auto_on_qualified"},
        )

        await self._notification.send_invitation_email(
            candidate_email=candidate_email,
            interview_link=f"{self._settings.FRONTEND_ORIGIN}/interview/{token}",
        )
