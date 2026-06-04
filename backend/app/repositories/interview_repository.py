from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview_message import InterviewMessage
from app.models.interview_session import InterviewSession


class InterviewSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_interview_token(self, token: str) -> InterviewSession | None:
        """Bypasses RLS — token is the authenticator for candidate access."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT s.* FROM interview_sessions s
                JOIN applications a ON a.id = s.application_id
                WHERE a.interview_token = :token
                  AND a.interview_token_expires_at > now()
                LIMIT 1
                """
            ),
            {"token": token},
        )
        row = result.mappings().first()
        if not row:
            return None
        sess = InterviewSession.__new__(InterviewSession)
        for k, v in row.items():
            object.__setattr__(sess, k, v)
        return sess

    async def get_or_create_for_token(self, token: str) -> InterviewSession | None:
        existing = await self.get_by_interview_token(token)
        if existing:
            return existing
        # Token is valid but session not created yet — create it
        result = await self._session.execute(
            sa.text(
                """
                SELECT a.id as application_id, a.company_id
                FROM applications a
                WHERE a.interview_token = :token
                  AND a.interview_token_expires_at > now()
                LIMIT 1
                """
            ),
            {"token": token},
        )
        row = result.mappings().first()
        if not row:
            return None

        sess = InterviewSession(
            id=str(uuid.uuid4()),
            application_id=str(row["application_id"]),
            company_id=str(row["company_id"]),
            mode="voice",
            status="pending",
            turn_count=0,
            max_turns=20,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(sess)
        await self._session.flush()
        return sess

    async def update_status(self, session_id: str, status: str) -> None:
        updates: dict = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if status == "in_progress":
            updates["started_at"] = datetime.now(timezone.utc)
        elif status in ("completed", "expired", "system_interrupted", "abandoned"):
            updates["completed_at"] = datetime.now(timezone.utc)
        await self._session.execute(
            sa.update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(**updates)
        )

    async def increment_turn(self, session_id: str) -> None:
        await self._session.execute(
            sa.update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(
                turn_count=InterviewSession.turn_count + 1,
                last_active_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def get_sessions_to_expire(self) -> list[str]:
        """Return IDs of sessions with last_active_at older than 24h in 'in_progress' or 'system_interrupted'."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT id FROM interview_sessions
                WHERE status IN ('in_progress', 'system_interrupted')
                  AND last_active_at < now() - interval '24 hours'
                """
            )
        )
        return [str(r[0]) for r in result.fetchall()]


class InterviewMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append_message(
        self,
        *,
        session_id: str,
        company_id: str,
        turn_index: int,
        speaker: str,
        content_text: str,
        audio_blob_key: str | None = None,
        is_blocked: bool = False,
    ) -> InterviewMessage:
        msg = InterviewMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            company_id=company_id,
            turn_index=turn_index,
            speaker=speaker,
            content_text="[blocked]" if is_blocked else content_text,
            audio_blob_key=audio_blob_key,
            is_blocked=is_blocked,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(msg)
        await self._session.flush()
        return msg

    async def list_by_session(self, session_id: str) -> list[InterviewMessage]:
        result = await self._session.execute(
            sa.select(InterviewMessage)
            .where(InterviewMessage.session_id == session_id)
            .order_by(InterviewMessage.turn_index)
        )
        return list(result.scalars().all())
