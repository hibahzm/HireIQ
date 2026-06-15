from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, name: str) -> Company:
        company = Company(
            id=str(uuid.uuid4()),
            name=name,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._session.add(company)
        await self._session.flush()
        return company

    async def get_by_id(self, company_id: str) -> Company | None:
        result = await self._session.execute(sa.select(Company).where(Company.id == company_id))
        return result.scalar_one_or_none()

    async def update_overview(self, company_id: str, overview: str | None) -> Company | None:
        await self._session.execute(
            sa.update(Company)
            .where(Company.id == company_id)
            .values(overview=overview, updated_at=datetime.now(UTC))
        )
        return await self.get_by_id(company_id)
