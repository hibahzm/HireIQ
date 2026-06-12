from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_authed_session, require_admin, require_recruiter_or_admin
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.company_repository import CompanyRepository

router = APIRouter(prefix="/company", tags=["company"])


class CompanyResponse(BaseModel):
    id: str
    name: str
    overview: str | None = None


class CompanyOverviewRequest(BaseModel):
    overview: str | None = Field(default=None, max_length=4000)


@router.get("", response_model=CompanyResponse)
async def get_company(
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    company = await CompanyRepository(session).get_by_id(current_user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyResponse(id=str(company.id), name=company.name, overview=company.overview)


@router.put("/overview", response_model=CompanyResponse)
async def update_company_overview(
    body: CompanyOverviewRequest,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_authed_session),
):
    """Admin-edited blurb Sila uses to answer candidate questions about the company."""
    overview = (body.overview or "").strip() or None
    company = await CompanyRepository(session).update_overview(
        current_user.company_id, overview
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    await AuditLogRepository(session).log_event(
        event_type="company.overview_updated",
        actor_type="user",
        actor_id=current_user.id,
        entity_type="company",
        entity_id=str(company.id),
        company_id=current_user.company_id,
    )
    return CompanyResponse(id=str(company.id), name=company.name, overview=company.overview)
