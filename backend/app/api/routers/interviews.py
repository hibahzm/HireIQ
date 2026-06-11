from __future__ import annotations

import base64
import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db import _get_session_factory
from app.redis_client import _redis as get_redis_instance
from app.repositories.interview_repository import InterviewSessionRepository

logger = structlog.get_logger()

router = APIRouter(tags=["interviews"])


@router.websocket("/interviews/{token}/connect")
async def interview_connect(websocket: WebSocket, token: str) -> None:
    await websocket.accept()
    structlog.contextvars.bind_contextvars(interview_token=token[:8])

    async with _get_session_factory()() as session:
        async with session.begin():
            session_repo = InterviewSessionRepository(session)
            interview_session = await session_repo.get_or_create_for_token(token)

            if not interview_session:
                await websocket.send_json({"type": "session_expired", "message": "Invalid or expired interview link"})
                await websocket.close(code=1008)
                return

            session_id = interview_session.id
            company_id = interview_session.company_id
            is_resuming = interview_session.turn_count > 0
            streaming_mode = interview_session.streaming_mode

            # Load job criteria
            import sqlalchemy as sa
            from app.models.job_criteria import JobCriteria
            from app.models.application import Application

            result = await session.execute(
                sa.select(Application).where(Application.id == interview_session.application_id)
            )
            application = result.scalar_one_or_none()
            if not application:
                await websocket.send_json({"type": "error", "message": "Application not found"})
                await websocket.close(code=1011)
                return

            await session.execute(
                sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                {"cid": str(company_id)},
            )
            result = await session.execute(
                sa.select(JobCriteria).where(JobCriteria.job_id == application.job_id)
            )
            criteria_model = result.scalar_one_or_none()
            job_criteria = {}
            if criteria_model:
                job_criteria = {
                    "required_skills": criteria_model.required_skills,
                    "evaluation_dimensions": criteria_model.evaluation_dimensions,
                    "dealbreakers": criteria_model.dealbreakers,
                    "min_screening_score": criteria_model.min_screening_score,
                }

    async def _send_json(payload: dict) -> bool:
        try:
            await websocket.send_json(payload)
        except (RuntimeError, WebSocketDisconnect) as exc:
            logger.info("interview.ws_disconnected", session_id=session_id, error=str(exc))
            return False
        return True

    async def _close_websocket(code: int) -> None:
        try:
            await websocket.close(code=code)
        except RuntimeError:
            pass

    # Send session_ready (streaming_mode tells the client whether to start continuous capture)
    if not await _send_json({
        "type": "session_ready",
        "session_id": session_id,
        "resuming": is_resuming,
        "turn_count": interview_session.turn_count,
        "max_turns": interview_session.max_turns,
        "streaming_mode": streaming_mode,
    }):
        return

    async def _stream_ai_response(text: str, *, counts_as_turn: bool = True) -> bool:
        """Send the guardrail-approved AI text, then stream its TTS audio in chunks."""
        if not await _send_json({
            "type": "ai_turn_text",
            "text": text,
            "counts_as_turn": counts_as_turn,
        }):
            return False
        seq = 0
        try:
            from app.services.streaming_tts_service import StreamingTtsService

            async for chunk in StreamingTtsService().stream(text):
                if not await _send_json({
                    "type": "ai_audio_chunk",
                    "audio": base64.b64encode(chunk).decode(),
                    "seq": seq,
                }):
                    return False
                seq += 1
        except Exception as exc:
            logger.warning("interview.tts_stream_failed", session_id=session_id, error=str(exc))
        return await _send_json({"type": "ai_audio_end"})

    async def _log_streaming_fallback() -> None:
        """Record an audit event when the streaming path degrades to turn-based (Constitution VII)."""
        try:
            async with _get_session_factory()() as s:
                async with s.begin():
                    import sqlalchemy as sa
                    from app.repositories.audit_log_repository import AuditLogRepository

                    await s.execute(
                        sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                        {"cid": str(company_id)},
                    )
                    await AuditLogRepository(s).log_event(
                        event_type="interview.streaming_fallback",
                        actor_type="system",
                        entity_type="interview_session",
                        entity_id=session_id,
                        company_id=company_id,
                    )
        except Exception:
            pass

    if streaming_mode and not is_resuming and interview_session.turn_count == 0:
        if not await _stream_ai_response(
            (
                "Hello, welcome to your AI interview. "
                "Please start by telling me about your background and the experience "
                "most relevant to this role."
            ),
            counts_as_turn=False,
        ):
            return

    # Streaming-mode per-utterance state (lives across audio_frame messages)
    stt_service = None
    pcm_buffer = bytearray()

    # Main message loop
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type")

            # ── Streaming branch (client VAD drives audio_frame / end_of_speech) ──
            if streaming_mode and msg_type == "audio_frame":
                if stt_service is None:
                    try:
                        from app.services.streaming_stt_service import StreamingSttService

                        stt_service = StreamingSttService()
                        stt_service.start()
                        pcm_buffer = bytearray()
                    except Exception as exc:
                        logger.error("interview.stt_init_failed", session_id=session_id, error=str(exc))
                        await _log_streaming_fallback()
                        if not await _send_json({
                            "type": "service_error",
                            "message": "Streaming voice is unavailable. Your session is preserved — reconnect to continue.",
                        }):
                            return
                        break
                frame = base64.b64decode(msg.get("audio", ""))
                pcm_buffer.extend(frame)
                try:
                    stt_service.push(frame)
                except Exception as exc:
                    logger.warning("interview.stt_push_failed", session_id=session_id, error=str(exc))
                continue

            if streaming_mode and msg_type == "end_of_speech":
                if stt_service is None:
                    continue
                if not await _send_json({"type": "turn_processing"}):
                    return
                try:
                    candidate_text = await stt_service.finalize()
                except Exception as exc:
                    logger.warning("interview.stt_finalize_failed", session_id=session_id, error=str(exc))
                    candidate_text = ""
                captured_pcm = bytes(pcm_buffer)
                stt_service = None
                pcm_buffer = bytearray()
                if not candidate_text:
                    if not await _stream_ai_response(
                        "I didn't catch that - could you say it again?",
                        counts_as_turn=False,
                    ):
                        return
                    continue
                async with _get_session_factory()() as session:
                    async with session.begin():
                        import sqlalchemy as sa
                        await session.execute(
                            sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                            {"cid": str(company_id)},
                        )
                        from app.services.interview_service import InterviewService

                        try:
                            result = await InterviewService(session, get_redis_instance).handle_streaming_turn(
                                session_id=session_id,
                                company_id=company_id,
                                candidate_text=candidate_text,
                                candidate_pcm=captured_pcm,
                                job_criteria=job_criteria,
                            )
                        except Exception as exc:
                            logger.error("interview.streaming_turn_failed", session_id=session_id, error=str(exc))
                            if not await _send_json({
                                "type": "service_error",
                                "message": "An error occurred. Your session is preserved. Please reconnect to resume.",
                            }):
                                return
                            break
                if result.get("guardrail_triggered"):
                    if not await _send_json({"type": "turn_blocked", "message": result["ai_response"]}):
                        return
                else:
                    if not await _stream_ai_response(result["ai_response"]):
                        return
                    if result.get("session_complete"):
                        if not await _send_json({"type": "interview_complete"}):
                            return
                        await _close_websocket(code=1000)
                        return
                continue

            # ── Turn-based branch (default; also the streaming text fallback) ──
            if msg_type not in ("text_input", "audio_input"):
                continue

            if not await _send_json({"type": "turn_processing"}):
                return

            async with _get_session_factory()() as session:
                async with session.begin():
                    import sqlalchemy as sa
                    await session.execute(
                        sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                        {"cid": str(company_id)},
                    )
                    from app.services.interview_service import InterviewService
                    redis = get_redis_instance

                    svc = InterviewService(session, redis)

                    audio_bytes = None
                    mode = "text"
                    if msg_type == "audio_input":
                        audio_bytes = base64.b64decode(msg.get("audio", ""))
                        mode = "voice"

                    try:
                        result = await svc.handle_turn(
                            session_id=session_id,
                            company_id=company_id,
                            candidate_input=msg.get("text"),
                            audio_bytes=audio_bytes,
                            mode=mode,
                            job_criteria=job_criteria,
                        )
                    except Exception as exc:
                        logger.error("interview.turn_failed", session_id=session_id, error=str(exc))
                        if not await _send_json({
                            "type": "service_error",
                            "message": "An error occurred. Your session is preserved. Please reconnect to resume.",
                        }):
                            return
                        break

            if result.get("guardrail_triggered"):
                if not await _send_json({
                    "type": "turn_blocked",
                    "message": result["ai_response"],
                }):
                    return
            elif result.get("session_complete"):
                # Send final AI turn
                response_msg: dict = {
                    "type": "ai_turn",
                    "text": result["ai_response"],
                }
                if result.get("audio_bytes"):
                    response_msg["audio"] = base64.b64encode(result["audio_bytes"]).decode()
                if not await _send_json(response_msg):
                    return
                if not await _send_json({"type": "interview_complete"}):
                    return
                await _close_websocket(code=1000)
                return
            else:
                response_msg = {
                    "type": "ai_turn",
                    "text": result["ai_response"],
                }
                if result.get("audio_bytes"):
                    response_msg["audio"] = base64.b64encode(result["audio_bytes"]).decode()
                if not await _send_json(response_msg):
                    return

    except WebSocketDisconnect:
        logger.info("interview.ws_disconnected", session_id=session_id)
    except Exception as exc:
        logger.error("interview.ws_error", session_id=session_id, error=str(exc))
        await _close_websocket(code=1011)
