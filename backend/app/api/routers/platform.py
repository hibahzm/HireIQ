from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import require_manager
from app.db import _get_session_factory
from app.models.user import User

router = APIRouter(prefix="/platform", tags=["platform"])


class PlatformCompanySummary(BaseModel):
    id: str
    name: str
    activity_events: int
    job_events: int
    last_activity_at: datetime | None


class PlatformUsageSummary(BaseModel):
    company_id: str | None
    agent_type: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float


class PlatformAuditSummary(BaseModel):
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
                await session.execute(
                    sa.text(
                        """
                        SELECT
                            c.id,
                            c.name,
                            COUNT(a.id) AS activity_events,
                            COUNT(DISTINCT a.entity_id) FILTER (WHERE a.entity_type = 'job') AS job_events,
                            MAX(a.created_at) AS last_activity_at
                        FROM companies c
                        LEFT JOIN audit_logs a ON a.company_id = c.id
                        GROUP BY c.id, c.name
                        ORDER BY c.created_at DESC
                        LIMIT 100
                        """
                    )
                )
            ).mappings().all()

            usage = (
                await session.execute(
                    sa.text(
                        """
                        SELECT
                            company_id,
                            agent_type,
                            COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                            COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                            COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
                        FROM llm_usage_events
                        WHERE created_at >= date_trunc('month', now())
                        GROUP BY company_id, agent_type
                        ORDER BY estimated_cost_usd DESC
                        LIMIT 100
                        """
                    )
                )
            ).mappings().all()

            audit_events = (
                await session.execute(
                    sa.text(
                        """
                        SELECT event_type, COUNT(*) AS count
                        FROM audit_logs
                        WHERE created_at >= date_trunc('month', now())
                        GROUP BY event_type
                        ORDER BY count DESC, event_type
                        LIMIT 50
                        """
                    )
                )
            ).mappings().all()

    return PlatformOverviewResponse(
        companies=[
            PlatformCompanySummary(
                id=str(row["id"]),
                name=row["name"],
                activity_events=int(row["activity_events"]),
                job_events=int(row["job_events"]),
                last_activity_at=row["last_activity_at"],
            )
            for row in companies
        ],
        usage=[
            PlatformUsageSummary(
                company_id=str(row["company_id"]) if row["company_id"] else None,
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
            PlatformAuditSummary(event_type=row["event_type"], count=int(row["count"]))
            for row in audit_events
        ],
    )
