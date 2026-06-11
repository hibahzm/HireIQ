from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setup_conversation import SetupConversation


class SetupConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, *, job_id: str, company_id: str) -> SetupConversation:
        result = await self._session.execute(
            sa.select(SetupConversation).where(SetupConversation.job_id == job_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        conv = SetupConversation(
            id=str(uuid.uuid4()),
            job_id=job_id,
            company_id=company_id,
            messages=[],
            status="in_progress",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(conv)
        await self._session.flush()
        return conv

    async def append_message(
        self, conversation_id: str, role: str, content: str
    ) -> SetupConversation:
        result = await self._session.execute(
            sa.select(SetupConversation).where(SetupConversation.id == conversation_id)
        )
        conv = result.scalar_one()
        messages = list(conv.messages)
        messages.append({"role": role, "content": content})
        conv.messages = messages
        conv.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return conv

    async def complete(self, conversation_id: str) -> SetupConversation:
        result = await self._session.execute(
            sa.select(SetupConversation).where(SetupConversation.id == conversation_id)
        )
        conv = result.scalar_one()
        conv.status = "completed"
        conv.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return conv

    async def fail(self, conversation_id: str, message: str) -> SetupConversation:
        conv = await self.append_message(conversation_id, "assistant", message)
        conv.status = "failed"
        conv.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return conv
