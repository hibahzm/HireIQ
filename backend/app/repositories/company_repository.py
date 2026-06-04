from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(company)
        await self._session.flush()
        return company

    async def get_by_id(self, company_id: str) -> Company | None:
        result = await self._session.execute(
            sa.select(Company).where(Company.id == company_id)
        )
        return result.scalar_one_or_none()
