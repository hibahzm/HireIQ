from __future__ import annotations

import base64
import json
import uuid

import structlog
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.interview_repository import (
    DEFAULT_INTERVIEW_MAX_TURNS,
    InterviewMessageRepository,
    InterviewSessionRepository,
)
from app.services.stt_service import SttService
from app.services.storage_service import StorageService
from app.services.tts_service import TtsService
from app.services.usage_service import record_usage_events

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

    @staticmethod
    def _dimension_names(job_criteria: dict) -> list[str]:
        names: list[str] = []
        for dimension in job_criteria.get("evaluation_dimensions") or []:
            value = None
            if isinstance(dimension, dict):
                value = (
                    dimension.get("name")
                    or dimension.get("dimension")
                    or dimension.get("label")
                    or dimension.get("title")
                )
            elif isinstance(dimension, str):
                value = dimension
            if value:
                names.append(str(value))
        return names

    @staticmethod
    def _updated_interview_state(
        *,
        previous_state: dict,
        agent_result: dict,
        history: list[dict[str, str]],
        new_turn_count: int,
        max_turns: int,
    ) -> dict:
        updated_state = agent_result.get("updated_state") or {}
        dimensions_remaining = (
            agent_result.get("dimensions_remaining")
            or updated_state.get("dimensions_remaining")
            or previous_state.get("dimensions_remaining")
            or []
        )
        return {
            **previous_state,
            "conversation_history": history,
            "dimensions_covered": updated_state.get(
                "dimensions_covered",
                previous_state.get("dimensions_covered", []),
            ),
            "dimensions_remaining": dimensions_remaining,
            "turn_count": new_turn_count,
            "max_turns": max_turns,
        }

    @staticmethod
    def _effective_max_turns(value: int | None = None) -> int:
        try:
            max_turns = int(value or DEFAULT_INTERVIEW_MAX_TURNS)
        except (TypeError, ValueError):
            max_turns = DEFAULT_INTERVIEW_MAX_TURNS
        return min(max_turns, DEFAULT_INTERVIEW_MAX_TURNS)

    @staticmethod
    def _effective_turn_count(state_value: object, fallback: int | None = None) -> int:
        try:
            state_turn_count = max(int(state_value or 0), 0)
        except (TypeError, ValueError):
            state_turn_count = 0
        try:
            fallback_turn_count = max(int(fallback or 0), 0)
        except (TypeError, ValueError):
            fallback_turn_count = 0
        return max(state_turn_count, fallback_turn_count)

    @staticmethod
    def _candidate_wants_to_stop(text: str) -> bool:
        normalized = " ".join(text.lower().replace("'", "").split())
        stop_phrases = (
            "i dont want to continue",
            "i do not want to continue",
            "i want to stop",
            "i need to stop",
            "stop the interview",
            "end the interview",
            "quit the interview",
            "cancel the interview",
            "i am done with this interview",
            "im done with this interview",
            "i dont want this interview",
            "i do not want this interview",
        )
        return any(phrase in normalized for phrase in stop_phrases)

    async def _complete_at_candidate_request(
        self,
        *,
        session_id: str,
        company_id: str,
        candidate_text: str,
        audio_key: str | None,
        history: list[dict[str, str]],
        state: dict,
        state_turn_count: int,
        effective_max_turns: int,
    ) -> dict:
        session_repo = InterviewSessionRepository(self._session)
        message_repo = InterviewMessageRepository(self._session)
        audit = AuditLogRepository(self._session)
        ai_text = (
            "Thank you for your time. I'll end the interview here, "
            "and the team will review your responses."
        )
        turn_index = state_turn_count * 2

        await message_repo.append_message(
            session_id=session_id,
            company_id=company_id,
            turn_index=turn_index,
            speaker="candidate",
            content_text=candidate_text,
            audio_blob_key=audio_key,
        )
        await message_repo.append_message(
            session_id=session_id,
            company_id=company_id,
            turn_index=turn_index + 1,
            speaker="ai",
            content_text=ai_text,
        )

        new_turn_count = state_turn_count + 1
        history.append({"role": "assistant", "content": ai_text})
        await self._save_redis_state(
            session_id,
            {
                **state,
                "conversation_history": history,
                "turn_count": new_turn_count,
                "max_turns": effective_max_turns,
            },
        )
        await session_repo.increment_turn(session_id)
        await session_repo.update_status(session_id, "completed")
        await audit.log_event(
            event_type="interview.candidate_ended",
            actor_type="candidate",
            entity_type="interview_session",
            entity_id=session_id,
            company_id=company_id,
        )

        import asyncio

        asyncio.create_task(self._trigger_evaluation(session_id, company_id))
        return {
            "ai_response": ai_text,
            "session_complete": True,
            "audio_bytes": None,
            "guardrail_triggered": False,
            "candidate_ended": True,
        }

    async def _conversation_history(
        self,
        message_repo: InterviewMessageRepository,
        session_id: str,
        state: dict,
    ) -> list[dict[str, str]]:
        history = state.get("conversation_history")
        if isinstance(history, list) and history:
            return list(history)

        messages = await message_repo.list_by_session(session_id)
        return [
            {
                "role": "user" if message.speaker == "candidate" else "assistant",
                "content": message.content_text,
            }
            for message in messages
            if message.content_text
        ]

    async def handle_turn(
        self,
        *,
        session_id: str,
        company_id: str,
        candidate_input: str | None = None,
        audio_bytes: bytes | None = None,
        mode: str = "text",
        job_criteria: dict,
        max_turns: int | None = None,
        current_turn_count: int | None = None,
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
        effective_max_turns = self._effective_max_turns(max_turns or state.get("max_turns"))
        state_turn_count = self._effective_turn_count(state.get("turn_count"), current_turn_count)

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
        history = await self._conversation_history(message_repo, session_id, state)
        history.append({"role": "user", "content": candidate_text})

        # Update session status to in_progress on first turn
        await session_repo.update_status(session_id, "in_progress")

        if self._candidate_wants_to_stop(candidate_text):
            result = await self._complete_at_candidate_request(
                session_id=session_id,
                company_id=company_id,
                candidate_text=candidate_text,
                audio_key=audio_key,
                history=history,
                state=state,
                state_turn_count=state_turn_count,
                effective_max_turns=effective_max_turns,
            )
            if mode == "voice":
                try:
                    result["audio_bytes"] = await self._tts.synthesize(result["ai_response"])
                except Exception as exc:
                    logger.warning("tts.failed", session_id=session_id, error=str(exc))
            return result

        # Call agents interview/turn
        import httpx

        payload = jsonable_encoder({
            "company_id": company_id,
            "session_id": session_id,
            "conversation_history": history,
            "dimensions_covered": state.get("dimensions_covered", []),
            "dimensions_remaining": state.get(
                "dimensions_remaining",
                self._dimension_names(job_criteria),
            ),
            "turn_count": state_turn_count,
            "max_turns": effective_max_turns,
            "job_criteria": job_criteria,
        })

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
        await record_usage_events(
            self._session,
            company_id=company_id,
            events=agent_result.get("usage_events"),
            metadata={"session_id": session_id},
        )

        ai_text = agent_result["ai_response"]
        guardrail_triggered = agent_result.get("guardrail_triggered", False)
        session_complete = agent_result.get("session_complete", False)

        # Persist candidate turn
        turn_index = state_turn_count * 2
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
        new_turn_count = state_turn_count + 1
        history.append({"role": "assistant", "content": ai_text})
        new_state = self._updated_interview_state(
            previous_state=state,
            agent_result=agent_result,
            history=history,
            new_turn_count=new_turn_count,
            max_turns=effective_max_turns,
        )
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
        max_turns: int | None = None,
        current_turn_count: int | None = None,
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
        effective_max_turns = self._effective_max_turns(max_turns or state.get("max_turns"))
        state_turn_count = self._effective_turn_count(state.get("turn_count"), current_turn_count)

        # Assemble + store the candidate's streamed audio so audio_blob_key has parity
        # with the turn-based path (FR-006 / SC-003).
        audio_key = None
        if candidate_pcm:
            audio_key = f"interviews/{session_id}/{str(uuid.uuid4())}.wav"
            await self._storage.upload(audio_key, self._pcm_to_wav(candidate_pcm))

        history = await self._conversation_history(message_repo, session_id, state)
        history.append({"role": "user", "content": candidate_text})

        await session_repo.update_status(session_id, "in_progress")

        if self._candidate_wants_to_stop(candidate_text):
            return await self._complete_at_candidate_request(
                session_id=session_id,
                company_id=company_id,
                candidate_text=candidate_text,
                audio_key=audio_key,
                history=history,
                state=state,
                state_turn_count=state_turn_count,
                effective_max_turns=effective_max_turns,
            )

        import httpx

        payload = jsonable_encoder({
            "company_id": company_id,
            "session_id": session_id,
            "conversation_history": history,
            "dimensions_covered": state.get("dimensions_covered", []),
            "dimensions_remaining": state.get(
                "dimensions_remaining",
                self._dimension_names(job_criteria),
            ),
            "turn_count": state_turn_count,
            "max_turns": effective_max_turns,
            "job_criteria": job_criteria,
        })

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
        await record_usage_events(
            self._session,
            company_id=company_id,
            events=agent_result.get("usage_events"),
            metadata={"session_id": session_id, "mode": "streaming"},
        )

        ai_text = agent_result["ai_response"]
        guardrail_triggered = agent_result.get("guardrail_triggered", False)
        session_complete = agent_result.get("session_complete", False)

        turn_index = state_turn_count * 2
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

        new_turn_count = state_turn_count + 1
        history.append({"role": "assistant", "content": ai_text})
        new_state = self._updated_interview_state(
            previous_state=state,
            agent_result=agent_result,
            history=history,
            new_turn_count=new_turn_count,
            max_turns=effective_max_turns,
        )
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
        if self._redis is None:
            logger.warning("interview.redis_unavailable", session_id=session_id)
            return {}
        try:
            raw = await self._redis.get(self._redis_key(session_id))
        except Exception as exc:
            logger.warning("interview.redis_load_failed", session_id=session_id, error=str(exc))
            return {}
        if raw:
            try:
                state = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                return {}
            return state if isinstance(state, dict) else {}
        return {}

    async def _save_redis_state(self, session_id: str, state: dict) -> None:
        if self._redis is None:
            logger.warning("interview.redis_unavailable", session_id=session_id)
            return
        try:
            await self._redis.set(
                self._redis_key(session_id),
                json.dumps(state),
                ex=REDIS_SESSION_TTL,
            )
        except Exception as exc:
            logger.warning("interview.redis_save_failed", session_id=session_id, error=str(exc))

    async def _trigger_evaluation(self, session_id: str, company_id: str) -> None:
        from app.db import _get_session_factory
        import sqlalchemy as sa

        async with _get_session_factory()() as db_session:
            async with db_session.begin():
                await db_session.execute(
                    sa.text("SELECT set_config('app.current_company_id', :cid, true)"), {"cid": company_id}
                )
                from app.services.evaluation_service import EvaluationService
                svc = EvaluationService(db_session, self._redis)
                await svc.evaluate_from_session(session_id=session_id, company_id=company_id)
