from __future__ import annotations

import structlog
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.repositories.application_repository import ApplicationRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.cv_chunk_repository import CvChunkRepository
from app.services.embedding_service import EmbeddingService
from app.services.notification_service import NotificationService
from app.services.ocr_service import OcrService, OcrValidationError
from app.services.storage_service import StorageService

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
                    logger.warning("screening.no_criteria", job_id=job_id)
                    return
                job_criteria = {
                    "required_skills": criteria_model.required_skills,
                    "optional_skills": criteria_model.optional_skills,
                    "experience_level": criteria_model.experience_level,
                    "evaluation_dimensions": criteria_model.evaluation_dimensions,
                    "dealbreakers": criteria_model.dealbreakers,
                    "min_screening_score": criteria_model.min_screening_score,
                }
                svc = ScreeningService(session)
                await svc.screen(
                    application_id=application_id,
                    company_id=company_id,
                    job_title=job_title,
                    candidate_email=candidate_email,
                    job_criteria=job_criteria,
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
                    await ApplicationRepository(session).update_screening_status(
                        application_id, "failed"
                    )
        except Exception:
            logger.exception("screening.failed_status_update", application_id=application_id)


class ScreeningService:
    def __init__(self, session: AsyncSession, redis=None) -> None:
        self._session = session
        self._settings = get_settings()
        self._storage = StorageService()
        self._ocr = OcrService()
        self._embedding = EmbeddingService()
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
    ) -> None:
        """Orchestrate: OCR → chunk+embed → hybrid search → agents /cv-screen → persist."""
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

        # 2. OCR
        try:
            cv_text, extraction_method = await self._ocr.extract(cv_bytes)
        except OcrValidationError as exc:
            logger.error("cv.ocr.failed", application_id=application_id, error=str(exc))
            return

        # 3. Chunk + embed
        chunks = await self._embedding.embed_chunks(cv_text)
        cv_chunk_repo = CvChunkRepository(self._session)
        await cv_chunk_repo.bulk_insert(application_id, company_id, chunks)

        # 4. Hybrid search for context
        if chunks:
            query_text = cv_text[:500]
            query_embedding = chunks[0][1]
            search_results = await cv_chunk_repo.hybrid_search(
                job_id=job_id,
                query_embedding=query_embedding,
                query_text=query_text,
            )
        else:
            search_results = []

        # 5. Call agents /cv-screen
        import httpx

        payload = jsonable_encoder({
            "application_id": application_id,
            "company_id": company_id,
            "cv_text": cv_text,
            "job_criteria": job_criteria,
            "hybrid_search_results": search_results,
        })
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._settings.AGENTS_BASE_URL}/agents/cv-screen",
                json=payload,
                headers={"X-Internal-Secret": self._settings.AGENTS_INTERNAL_SECRET},
            )
            resp.raise_for_status()
        agent_result = resp.json()

        # 6. Persist results
        final_status = "qualified" if agent_result["status"] == "qualified" else "rejected"
        await app_repo.update_screening_result(
            application_id,
            cv_text=cv_text,
            cv_extraction_method=extraction_method,
            screening_score=agent_result["score"],
            screening_rationale=agent_result["rationale"],
            screening_status=agent_result["status"],
            status=final_status,
        )

        await audit.log_event(
            event_type="cv.screening.completed",
            actor_type="system",
            entity_type="application",
            entity_id=application_id,
            company_id=company_id,
            metadata={"score": agent_result["score"], "status": agent_result["status"]},
        )

        # 7. Send confirmation email
        await self._notification.send_confirmation_email(
            candidate_email=candidate_email,
            job_title=job_title,
        )
