from __future__ import annotations

import base64
import json
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.interview_repository import (
    InterviewMessageRepository,
    InterviewSessionRepository,
)
from app.services.stt_service import SttService
from app.services.storage_service import StorageService
from app.services.tts_service import TtsService

logger = structlog.get_logger()

REDIS_SESSION_TTL = 25 * 3600  # 25 hours


class InterviewService:
    def __init__(self, session: AsyncSession, redis) -> None:
        self._session = session
        self._redis = redis
        self._settings = get_settings()
        self._stt = SttService()
        self._tts = TtsService()
        self._storage = StorageService()

    async def handle_turn(
        self,
        *,
        session_id: str,
        company_id: str,
        candidate_input: str | None = None,
        audio_bytes: bytes | None = None,
        mode: str = "text",
        job_criteria: dict,
    ) -> dict:
        """
        Process one interview turn. Returns dict with ai_response, session_complete,
        audio_bytes (if TTS enabled), guardrail_triggered.
        """
        session_repo = InterviewSessionRepository(self._session)
        message_repo = InterviewMessageRepository(self._session)
        audit = AuditLogRepository(self._session)

        # Load Redis state
        state = await self._load_redis_state(session_id)

        # STT if voice mode
        audio_key = None
        if mode == "voice" and audio_bytes:
            # Store raw audio before discarding
            audio_key = f"interviews/{session_id}/{str(uuid.uuid4())}.webm"
            await self._storage.upload(audio_key, audio_bytes)
            try:
                candidate_text = await self._stt.transcribe(audio_bytes)
            except ValueError as exc:
                if "empty_transcript" in str(exc):
                    # Candidate was silent — return a prompt without consuming a turn
                    logger.info("interview.empty_audio", session_id=session_id)
                    ai_prompt = (
                        "I didn't catch that. Could you speak a bit louder "
                        "or switch to text input using the toggle below?"
                    )
                    ai_audio = None
                    if mode == "voice":
                        try:
                            ai_audio = await self._tts.synthesize(ai_prompt)
                        except Exception:
                            pass
                    return {
                        "ai_response": ai_prompt,
                        "session_complete": False,
                        "audio_bytes": ai_audio,
                        "guardrail_triggered": False,
                        "empty_audio": True,
                    }
                raise
        else:
            candidate_text = candidate_input or ""

        # Append candidate message to state history
        history = state.get("conversation_history", [])
        history.append({"role": "user", "content": candidate_text})

        # Update session status to in_progress on first turn
        await session_repo.update_status(session_id, "in_progress")

        # Call agents interview/turn
        import httpx

        payload = {
            "conversation_history": history,
            "dimensions_covered": state.get("dimensions_covered", []),
            "dimensions_remaining": state.get("dimensions_remaining", list(
                d.get("name", "") for d in job_criteria.get("evaluation_dimensions", [])
            )),
            "turn_count": state.get("turn_count", 0),
            "max_turns": state.get("max_turns", 20),
            "job_criteria": job_criteria,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._settings.AGENTS_BASE_URL}/agents/interview/turn",
                    json=payload,
                    headers={"X-Internal-Secret": self._settings.AGENTS_INTERNAL_SECRET},
                )
                resp.raise_for_status()
            agent_result = resp.json()
        except Exception as exc:
            logger.error("interview.agents_call_failed", session_id=session_id, error=str(exc))
            await self.handle_system_interrupt(session_id)
            raise

        ai_text = agent_result["ai_response"]
        guardrail_triggered = agent_result.get("guardrail_triggered", False)
        session_complete = agent_result.get("session_complete", False)

        # Persist candidate turn
        turn_index = state.get("turn_count", 0) * 2
        await message_repo.append_message(
            session_id=session_id,
            company_id=company_id,
            turn_index=turn_index,
            speaker="candidate",
            content_text=candidate_text,
            audio_blob_key=audio_key,
            is_blocked=guardrail_triggered,
        )

        # Persist AI turn
        await message_repo.append_message(
            session_id=session_id,
            company_id=company_id,
            turn_index=turn_index + 1,
            speaker="ai",
            content_text=ai_text,
        )

        if guardrail_triggered:
            await audit.log_event(
                event_type="interview.turn.blocked",
                actor_type="system",
                entity_type="interview_session",
                entity_id=session_id,
                company_id=company_id,
            )

        # Update state
        new_turn_count = state.get("turn_count", 0) + 1
        history.append({"role": "assistant", "content": ai_text})
        new_state = {
            **state,
            "conversation_history": history,
            "dimensions_covered": agent_result["updated_state"].get("dimensions_covered", []),
            "dimensions_remaining": agent_result.get("dimensions_remaining", []),
            "turn_count": new_turn_count,
        }
        await self._save_redis_state(session_id, new_state)
        await session_repo.increment_turn(session_id)

        if session_complete:
            await session_repo.update_status(session_id, "completed")
            # Trigger evaluation asynchronously
            import asyncio
            asyncio.create_task(self._trigger_evaluation(session_id, company_id))

        # TTS
        ai_audio = None
        if mode == "voice":
            try:
                ai_audio = await self._tts.synthesize(ai_text)
            except Exception as exc:
                logger.warning("tts.failed", session_id=session_id, error=str(exc))

        return {
            "ai_response": ai_text,
            "session_complete": session_complete,
            "audio_bytes": ai_audio,
            "guardrail_triggered": guardrail_triggered,
        }

    @staticmethod
    def _pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
        """Wrap raw PCM16 mono audio in a WAV container so it stores like a turn-based blob."""
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(pcm)
        return buf.getvalue()

    async def handle_streaming_turn(
        self,
        *,
        session_id: str,
        company_id: str,
        candidate_text: str,
        candidate_pcm: bytes | None,
        job_criteria: dict,
    ) -> dict:
        """
        Process one streaming turn from an already-finalized transcript. Runs the same
        turn-core as handle_turn (guardrails → persist → state → evaluation) but does NOT
        synthesize audio — the WS layer streams TTS for the guardrail-approved text, so
        blocked content is never spoken (FR-007). Returns ai_response, session_complete,
        guardrail_triggered.
        """
        session_repo = InterviewSessionRepository(self._session)
        message_repo = InterviewMessageRepository(self._session)
        audit = AuditLogRepository(self._session)

        state = await self._load_redis_state(session_id)

        # Assemble + store the candidate's streamed audio so audio_blob_key has parity
        # with the turn-based path (FR-006 / SC-003).
        audio_key = None
        if candidate_pcm:
            audio_key = f"interviews/{session_id}/{str(uuid.uuid4())}.wav"
            await self._storage.upload(audio_key, self._pcm_to_wav(candidate_pcm))

        history = state.get("conversation_history", [])
        history.append({"role": "user", "content": candidate_text})

        await session_repo.update_status(session_id, "in_progress")

        import httpx

        payload = {
            "conversation_history": history,
            "dimensions_covered": state.get("dimensions_covered", []),
            "dimensions_remaining": state.get("dimensions_remaining", list(
                d.get("name", "") for d in job_criteria.get("evaluation_dimensions", [])
            )),
            "turn_count": state.get("turn_count", 0),
            "max_turns": state.get("max_turns", 20),
            "job_criteria": job_criteria,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._settings.AGENTS_BASE_URL}/agents/interview/turn",
                    json=payload,
                    headers={"X-Internal-Secret": self._settings.AGENTS_INTERNAL_SECRET},
                )
                resp.raise_for_status()
            agent_result = resp.json()
        except Exception as exc:
            logger.error("interview.agents_call_failed", session_id=session_id, error=str(exc))
            await self.handle_system_interrupt(session_id)
            raise

        ai_text = agent_result["ai_response"]
        guardrail_triggered = agent_result.get("guardrail_triggered", False)
        session_complete = agent_result.get("session_complete", False)

        turn_index = state.get("turn_count", 0) * 2
        await message_repo.append_message(
            session_id=session_id,
            company_id=company_id,
            turn_index=turn_index,
            speaker="candidate",
            content_text=candidate_text,
            audio_blob_key=audio_key,
            is_blocked=guardrail_triggered,
        )
        await message_repo.append_message(
            session_id=session_id,
            company_id=company_id,
            turn_index=turn_index + 1,
            speaker="ai",
            content_text=ai_text,
        )

        if guardrail_triggered:
            await audit.log_event(
                event_type="interview.turn.blocked",
                actor_type="system",
                entity_type="interview_session",
                entity_id=session_id,
                company_id=company_id,
            )

        new_turn_count = state.get("turn_count", 0) + 1
        history.append({"role": "assistant", "content": ai_text})
        new_state = {
            **state,
            "conversation_history": history,
            "dimensions_covered": agent_result["updated_state"].get("dimensions_covered", []),
            "dimensions_remaining": agent_result.get("dimensions_remaining", []),
            "turn_count": new_turn_count,
        }
        await self._save_redis_state(session_id, new_state)
        await session_repo.increment_turn(session_id)

        if session_complete:
            await session_repo.update_status(session_id, "completed")
            import asyncio
            asyncio.create_task(self._trigger_evaluation(session_id, company_id))

        return {
            "ai_response": ai_text,
            "session_complete": session_complete,
            "guardrail_triggered": guardrail_triggered,
        }

    async def handle_system_interrupt(self, session_id: str) -> None:
        session_repo = InterviewSessionRepository(self._session)
        audit = AuditLogRepository(self._session)

        await session_repo.update_status(session_id, "system_interrupted")
        await audit.log_event(
            event_type="interview.system_interrupted",
            actor_type="system",
            entity_type="interview_session",
            entity_id=session_id,
        )

    async def check_and_expire_sessions(self) -> None:
        """Called by APScheduler — expires stale sessions."""
        session_repo = InterviewSessionRepository(self._session)
        stale_ids = await session_repo.get_sessions_to_expire()
        for session_id in stale_ids:
            await session_repo.update_status(session_id, "abandoned")
            logger.info("interview.session_expired", session_id=session_id)

    # ── Redis state ──────────────────────────────────────────────────────────

    def _redis_key(self, session_id: str) -> str:
        return f"interview_session:{session_id}"

    async def _load_redis_state(self, session_id: str) -> dict:
        raw = await self._redis.get(self._redis_key(session_id))
        if raw:
            return json.loads(raw)
        return {}

    async def _save_redis_state(self, session_id: str, state: dict) -> None:
        await self._redis.set(
            self._redis_key(session_id),
            json.dumps(state),
            ex=REDIS_SESSION_TTL,
        )

    async def _trigger_evaluation(self, session_id: str, company_id: str) -> None:
        from app.db import _get_session_factory
        import sqlalchemy as sa

        async with _get_session_factory()() as db_session:
            async with db_session.begin():
                await db_session.execute(
                    sa.text("SET LOCAL app.current_company_id = :cid"), {"cid": company_id}
                )
                from app.services.evaluation_service import EvaluationService
                svc = EvaluationService(db_session, self._redis)
                await svc.evaluate_from_session(session_id=session_id, company_id=company_id)
