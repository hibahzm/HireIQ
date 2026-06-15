from __future__ import annotations

import uuid
from datetime import UTC, datetime

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
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_id(self, user_id: str, company_id: str | None = None) -> User | None:
        # company_id: explicit tenant scoping in addition to RLS (a privileged
        # DB role silently bypasses RLS policies).
        q = sa.select(User).where(User.id == user_id)
        if company_id:
            q = q.where(User.company_id == company_id)
        result = await self._session.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    def _user_from_row(row) -> User | None:
        if not row:
            return None
        data = dict(row)
        for key in ("id", "company_id"):
            if data.get(key) is not None:
                data[key] = str(data[key])
        return User(**data)

    async def get_by_email_global(self, email: str) -> User | None:
        """
        Global email lookup for login/registration (no company context yet).
        Goes through the SECURITY DEFINER function from migration 0016 because
        a direct SELECT is empty under the FORCE-RLS tenant policy.
        """
        result = await self._session.execute(
            sa.text("SELECT * FROM auth_find_user_by_email(:email)"),
            {"email": email},
        )
        return self._user_from_row(result.mappings().first())

    async def get_by_id_global(self, user_id: str) -> User | None:
        """Global id lookup for token refresh / invite flows (pre-RLS-context)."""
        result = await self._session.execute(
            sa.text("SELECT * FROM auth_find_user_by_id(:uid)"),
            {"uid": str(user_id)},
        )
        return self._user_from_row(result.mappings().first())

    async def list_by_company(self, company_id: str) -> list[User]:
        result = await self._session.execute(
            sa.select(User).where(User.company_id == company_id, User.role != "manager")
        )
        return list(result.scalars().all())

    async def count_active_admins(self, company_id: str) -> int:
        result = await self._session.execute(
            sa.select(sa.func.count())
            .select_from(User)
            .where(
                User.company_id == company_id,
                User.role == "admin",
                User.is_active.is_(True),
            )
        )
        return int(result.scalar_one())

    async def set_role(self, user_id: str, role: str) -> User | None:
        await self._session.execute(
            sa.update(User)
            .where(User.id == user_id)
            .values(role=role, updated_at=datetime.now(UTC))
        )
        return await self.get_by_id(user_id)

    async def deactivate(self, user_id: str) -> None:
        await self._session.execute(
            sa.update(User)
            .where(User.id == user_id)
            .values(is_active=False, updated_at=datetime.now(UTC))
        )
