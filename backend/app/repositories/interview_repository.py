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

    @staticmethod
    def _from_row(row) -> InterviewSession:
        data = dict(row)
        job_streaming_interview = bool(data.pop("job_streaming_interview", False))
        for key in ("id", "application_id", "company_id"):
            if data.get(key) is not None:
                data[key] = str(data[key])
        data["streaming_mode"] = bool(data.get("streaming_mode") or job_streaming_interview)
        return InterviewSession(**data)

    async def get_by_interview_token(self, token: str) -> InterviewSession | None:
        """Bypasses RLS — token is the authenticator for candidate access."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT s.*, COALESCE(j.streaming_interview, false) AS job_streaming_interview
                FROM interview_sessions s
                JOIN applications a ON a.id = s.application_id
                JOIN jobs j ON j.id = a.job_id
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
        session = self._from_row(row)
        if session.streaming_mode and not row["streaming_mode"]:
            await self._session.execute(
                sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                {"cid": session.company_id},
            )
            await self._session.execute(
                sa.update(InterviewSession)
                .where(InterviewSession.id == session.id)
                .values(streaming_mode=True, updated_at=datetime.now(timezone.utc))
            )
            await self._session.flush()
        return session

    async def get_or_create_for_token(self, token: str) -> InterviewSession | None:
        existing = await self.get_by_interview_token(token)
        if existing:
            return existing
        # Token is valid but session not created yet — create it
        result = await self._session.execute(
            sa.text(
                """
                SELECT a.id as application_id, a.company_id,
                       COALESCE(j.streaming_interview, false) AS streaming_interview
                FROM applications a
                JOIN jobs j ON j.id = a.job_id
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
            streaming_mode=bool(row["streaming_interview"]),
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

    async def list_by_application_id(self, application_id: str) -> list[dict]:
        """Return all turns for an application joined via interview_sessions."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT im.turn_index, im.speaker, im.content_text, im.audio_blob_key
                FROM interview_messages im
                JOIN interview_sessions s ON s.id = im.session_id
                JOIN applications a ON a.id = s.application_id
                WHERE a.id = :application_id
                ORDER BY im.turn_index
                """
            ),
            {"application_id": application_id},
        )
        return [dict(r) for r in result.mappings().all()]

    async def get_audio_blob_key(self, application_id: str, turn_index: int) -> str | None:
        """Return the audio_blob_key for a specific turn, looked up via application."""
        result = await self._session.execute(
            sa.text(
                """
                SELECT im.audio_blob_key
                FROM interview_messages im
                JOIN interview_sessions s ON s.id = im.session_id
                JOIN applications a ON a.id = s.application_id
                WHERE a.id = :application_id
                  AND im.turn_index = :turn_index
                LIMIT 1
                """
            ),
            {"application_id": application_id, "turn_index": turn_index},
        )
        row = result.mappings().first()
        if not row:
            return None
        return row["audio_blob_key"] or None
