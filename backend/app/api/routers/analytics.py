from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_authed_session, require_recruiter_or_admin
from app.models.user import User
from app.repositories.analytics_repository import AnalyticsRepository
from app.schemas.analytics import CompanyOverviewResponse, JobAnalyticsResponse
from app.services.analytics_service import AnalyticsService, JobNotFoundError

router = APIRouter(tags=["analytics"])


@router.get("/jobs/{job_id}/analytics", response_model=JobAnalyticsResponse)
async def get_job_analytics(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    """Per-job hiring-funnel analytics. Tenant-scoped via RLS; aggregates only."""
    service = AnalyticsService(AnalyticsRepository(session))
    try:
        return await service.get_job_analytics(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/analytics/overview", response_model=CompanyOverviewResponse)
async def get_company_overview(
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    """Company-wide KPIs for the current calendar month + the job list."""
    service = AnalyticsService(AnalyticsRepository(session))
    return await service.get_company_overview()
