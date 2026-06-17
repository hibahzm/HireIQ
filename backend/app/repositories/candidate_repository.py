from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate

# candidates is a global, no-RLS table, so direct SELECTs work without a tenant
# context (unlike `users`, which needs the SECURITY DEFINER resolvers).
_COLUMNS = "id, email, full_name, password_hash, is_active, open_to_work, created_at, updated_at"


class CandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _from_row(row) -> Candidate | None:
        if not row:
            return None
        data = dict(row)
        if data.get("id") is not None:
            data["id"] = str(data["id"])
        return Candidate(**data)

    async def get_or_create(self, *, email: str, full_name: str) -> Candidate:
        result = await self._session.execute(
            sa.text(f"SELECT {_COLUMNS} FROM candidates WHERE lower(email) = lower(:email)"),
            {"email": email},
        )
        row = result.mappings().first()
        if row:
            return self._from_row(row)

        cand = Candidate(
            id=str(uuid.uuid4()),
            email=email.lower(),
            full_name=full_name,
            created_at=datetime.now(UTC),
        )
        self._session.add(cand)
        await self._session.flush()
        return cand

    async def get_by_email(self, email: str) -> Candidate | None:
        result = await self._session.execute(
            sa.text(f"SELECT {_COLUMNS} FROM candidates WHERE lower(email) = lower(:email)"),
            {"email": email},
        )
        return self._from_row(result.mappings().first())

    async def get_by_id(self, candidate_id: str) -> Candidate | None:
        result = await self._session.execute(
            sa.text(f"SELECT {_COLUMNS} FROM candidates WHERE id = :cid"),
            {"cid": str(candidate_id)},
        )
        return self._from_row(result.mappings().first())

    async def create_account(
        self, *, email: str, full_name: str, password_hash: str
    ) -> Candidate:
        """Create a brand-new candidate account row."""
        cand = Candidate(
            id=str(uuid.uuid4()),
            email=email.lower(),
            full_name=full_name,
            password_hash=password_hash,
            is_active=True,
            open_to_work=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._session.add(cand)
        await self._session.flush()
        return cand

    async def set_account_credentials(
        self, *, candidate_id: str, full_name: str, password_hash: str
    ) -> Candidate | None:
        """Upgrade an existing apply-only record (no password) into an account."""
        await self._session.execute(
            sa.text(
                "UPDATE candidates SET password_hash = :ph, full_name = :fn, "
                "updated_at = now() WHERE id = :cid"
            ),
            {"ph": password_hash, "fn": full_name, "cid": str(candidate_id)},
        )
        return await self.get_by_id(candidate_id)

    async def update_profile(
        self,
        *,
        candidate_id: str,
        full_name: str | None = None,
        open_to_work: bool | None = None,
    ) -> Candidate | None:
        sets: list[str] = ["updated_at = now()"]
        params: dict = {"cid": str(candidate_id)}
        if full_name is not None:
            sets.append("full_name = :fn")
            params["fn"] = full_name
        if open_to_work is not None:
            sets.append("open_to_work = :otw")
            params["otw"] = open_to_work
        await self._session.execute(
            sa.text(f"UPDATE candidates SET {', '.join(sets)} WHERE id = :cid"), params
        )
        return await self.get_by_id(candidate_id)
