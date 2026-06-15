from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import require_manager
from app.db import _get_session_factory
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.services.storage_service import StorageService

router = APIRouter(prefix="/platform", tags=["platform"])
logger = structlog.get_logger()

PLATFORM_COMPANY_ID = "00000000-0000-0000-0000-000000000001"


class PlatformCompanySummary(BaseModel):
    id: str
    name: str
    activity_events: int
    job_events: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    last_activity_at: datetime | None


class PlatformUsageSummary(BaseModel):
    company_id: str | None
    company_name: str | None
    agent_type: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float


class PlatformAuditSummary(BaseModel):
    company_id: str | None
    company_name: str | None
    event_type: str
    count: int


class PlatformOverviewResponse(BaseModel):
    companies: list[PlatformCompanySummary]
    usage: list[PlatformUsageSummary]
    audit_events: list[PlatformAuditSummary]


@router.get("/overview", response_model=PlatformOverviewResponse)
async def get_platform_overview(
    current_user: User = Depends(require_manager),
) -> PlatformOverviewResponse:
    """
    Platform-manager overview. This intentionally returns aggregate operational
    data only: no CV text, interview transcript, candidate email, or company
    private payloads.
    """
    del current_user
    async with _get_session_factory()() as session:
        async with session.begin():
            companies = (
                (
                    await session.execute(
                        sa.text(
                            """
                        WITH company_activity AS (
                            SELECT
                                company_id,
                                COUNT(*) AS activity_events,
                                COUNT(DISTINCT entity_id) FILTER (WHERE entity_type = 'job') AS job_events,
                                MAX(created_at) AS last_activity_at
                            FROM audit_logs
                            WHERE company_id IS NOT NULL
                            GROUP BY company_id
                        ),
                        company_usage AS (
                            SELECT
                                company_id,
                                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                                COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
                            FROM llm_usage_events
                            WHERE created_at >= date_trunc('month', now())
                            GROUP BY company_id
                        )
                        SELECT
                            c.id,
                            c.name,
                            COALESCE(a.activity_events, 0) AS activity_events,
                            COALESCE(a.job_events, 0) AS job_events,
                            COALESCE(u.prompt_tokens, 0) AS prompt_tokens,
                            COALESCE(u.completion_tokens, 0) AS completion_tokens,
                            COALESCE(u.estimated_cost_usd, 0) AS estimated_cost_usd,
                            a.last_activity_at
                        FROM companies c
                        LEFT JOIN company_activity a ON a.company_id = c.id
                        LEFT JOIN company_usage u ON u.company_id = c.id
                        WHERE c.id <> CAST(:platform_company_id AS uuid)
                        ORDER BY c.created_at DESC
                        LIMIT 100
                        """
                        ),
                        {"platform_company_id": PLATFORM_COMPANY_ID},
                    )
                )
                .mappings()
                .all()
            )

            usage = (
                (
                    await session.execute(
                        sa.text(
                            """
                        SELECT
                            u.company_id,
                            c.name AS company_name,
                            u.agent_type,
                            COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                            COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                            COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
                        FROM llm_usage_events u
                        LEFT JOIN companies c ON c.id = u.company_id
                        WHERE u.created_at >= date_trunc('month', now())
                        AND (u.company_id IS NULL OR u.company_id <> CAST(:platform_company_id AS uuid))
                        GROUP BY u.company_id, c.name, u.agent_type
                        ORDER BY estimated_cost_usd DESC
                        LIMIT 100
                        """
                        ),
                        {"platform_company_id": PLATFORM_COMPANY_ID},
                    )
                )
                .mappings()
                .all()
            )

            audit_events = (
                (
                    await session.execute(
                        sa.text(
                            """
                        SELECT
                            a.company_id,
                            c.name AS company_name,
                            a.event_type,
                            COUNT(*) AS count
                        FROM audit_logs a
                        LEFT JOIN companies c ON c.id = a.company_id
                        WHERE a.created_at >= date_trunc('month', now())
                        AND (a.company_id IS NULL OR a.company_id <> CAST(:platform_company_id AS uuid))
                        GROUP BY a.company_id, c.name, a.event_type
                        ORDER BY count DESC, a.event_type
                        LIMIT 50
                        """
                        ),
                        {"platform_company_id": PLATFORM_COMPANY_ID},
                    )
                )
                .mappings()
                .all()
            )

    return PlatformOverviewResponse(
        companies=[
            PlatformCompanySummary(
                id=str(row["id"]),
                name=row["name"],
                activity_events=int(row["activity_events"]),
                job_events=int(row["job_events"]),
                prompt_tokens=int(row["prompt_tokens"]),
                completion_tokens=int(row["completion_tokens"]),
                estimated_cost_usd=float(
                    row["estimated_cost_usd"]
                    if isinstance(row["estimated_cost_usd"], Decimal)
                    else row["estimated_cost_usd"]
                ),
                last_activity_at=row["last_activity_at"],
            )
            for row in companies
        ],
        usage=[
            PlatformUsageSummary(
                company_id=str(row["company_id"]) if row["company_id"] else None,
                company_name=row["company_name"],
                agent_type=row["agent_type"],
                prompt_tokens=int(row["prompt_tokens"]),
                completion_tokens=int(row["completion_tokens"]),
                estimated_cost_usd=float(
                    row["estimated_cost_usd"]
                    if isinstance(row["estimated_cost_usd"], Decimal)
                    else row["estimated_cost_usd"]
                ),
            )
            for row in usage
        ],
        audit_events=[
            PlatformAuditSummary(
                company_id=str(row["company_id"]) if row["company_id"] else None,
                company_name=row["company_name"],
                event_type=row["event_type"],
                count=int(row["count"]),
            )
            for row in audit_events
        ],
    )


@router.delete(
    "/companies/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_company(
    company_id: str,
    current_user: User = Depends(require_manager),
) -> None:
    if company_id == PLATFORM_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Cannot delete the platform manager company")

    storage_keys: list[str] = []
    storage = StorageService()

    async with _get_session_factory()() as session:
        async with session.begin():
            row = (
                (
                    await session.execute(
                        sa.text("SELECT id, name FROM companies WHERE id = CAST(:id AS uuid)"),
                        {"id": company_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise HTTPException(status_code=404, detail="Company not found")

            await session.execute(
                sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                {"cid": company_id},
            )

            cv_keys = (
                (
                    await session.execute(
                        sa.text(
                            """
                        SELECT cv_blob_key AS key
                        FROM applications
                        WHERE company_id = CAST(:id AS uuid)
                        AND cv_blob_key IS NOT NULL
                        """
                        ),
                        {"id": company_id},
                    )
                )
                .scalars()
                .all()
            )
            audio_keys = (
                (
                    await session.execute(
                        sa.text(
                            """
                        SELECT audio_blob_key AS key
                        FROM interview_messages
                        WHERE company_id = CAST(:id AS uuid)
                        AND audio_blob_key IS NOT NULL
                        """
                        ),
                        {"id": company_id},
                    )
                )
                .scalars()
                .all()
            )
            storage_keys = [str(key) for key in [*cv_keys, *audio_keys] if key]

            await session.execute(
                sa.text("DELETE FROM llm_usage_events WHERE company_id = CAST(:id AS uuid)"),
                {"id": company_id},
            )

            await session.execute(
                sa.text("ALTER TABLE audit_logs DISABLE TRIGGER tg_audit_logs_no_update")
            )
            try:
                await session.execute(
                    sa.text("DELETE FROM audit_logs WHERE company_id = CAST(:id AS uuid)"),
                    {"id": company_id},
                )
            finally:
                await session.execute(
                    sa.text("ALTER TABLE audit_logs ENABLE TRIGGER tg_audit_logs_no_update")
                )

            await session.execute(
                sa.text("DELETE FROM companies WHERE id = CAST(:id AS uuid)"),
                {"id": company_id},
            )
            await session.execute(
                sa.text(
                    """
                    DELETE FROM candidates c
                    WHERE NOT EXISTS (
                        SELECT 1 FROM applications a WHERE a.candidate_id = c.id
                    )
                    """
                )
            )

            await AuditLogRepository(session).log_event(
                event_type="company.deleted",
                actor_type="user",
                actor_id=current_user.id,
                entity_type="company",
                entity_id=company_id,
                metadata={"company_name": row["name"]},
            )

    for key in storage_keys:
        try:
            await storage.delete(key)
        except Exception as exc:
            logger.warning("platform.company_storage_delete_failed", key=key, error=str(exc))
