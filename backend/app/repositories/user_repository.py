from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        company_id: str,
        email: str,
        password_hash: str,
        role: str,
    ) -> User:
        user = User(
            id=str(uuid.uuid4()),
            company_id=company_id,
            email=email.lower(),
            password_hash=password_hash,
            role=role,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self._session.execute(
            sa.select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email_global(self, email: str) -> User | None:
        """Bypasses RLS — used for login lookup only."""
        result = await self._session.execute(
            sa.text(
                "SELECT id, company_id, email, password_hash, role, is_active, created_at, updated_at "
                "FROM users WHERE lower(email) = lower(:email) LIMIT 1"
            ),
            {"email": email},
        )
        row = result.mappings().first()
        if not row:
            return None
        user = User.__new__(User)
        for key, value in row.items():
            object.__setattr__(user, key, value)
        return user

    async def list_by_company(self, company_id: str) -> list[User]:
        result = await self._session.execute(
            sa.select(User).where(User.company_id == company_id)
        )
        return list(result.scalars().all())

    async def set_role(self, user_id: str, role: str) -> User | None:
        await self._session.execute(
            sa.update(User)
            .where(User.id == user_id)
            .values(role=role, updated_at=datetime.now(timezone.utc))
        )
        return await self.get_by_id(user_id)

    async def deactivate(self, user_id: str) -> None:
        await self._session.execute(
            sa.update(User)
            .where(User.id == user_id)
            .values(is_active=False, updated_at=datetime.now(timezone.utc))
        )
