from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate


class CandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, *, email: str, full_name: str) -> Candidate:
        result = await self._session.execute(
            sa.text("SELECT id, email, full_name, created_at FROM candidates WHERE lower(email) = lower(:email)"),
            {"email": email},
        )
        row = result.mappings().first()
        if row:
            cand = Candidate.__new__(Candidate)
            for k, v in row.items():
                object.__setattr__(cand, k, v)
            return cand

        cand = Candidate(
            id=str(uuid.uuid4()),
            email=email.lower(),
            full_name=full_name,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(cand)
        await self._session.flush()
        return cand
