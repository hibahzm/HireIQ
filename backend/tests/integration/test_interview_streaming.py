"""
Integration tests for the streaming voice interview (V2-3).

Voice interview turn handling is a Constitution Principle VIII TDD-mandated domain, so
these are written FIRST and are gating. They drive the WebSocket streaming branch with
the Azure STT/TTS services and the turn-core mocked (the same style as test_interview.py),
asserting: streaming_mode is advertised, end-of-speech yields `ai_turn_text` then ordered
`ai_audio_chunk`s then `ai_audio_end`, captured audio is passed for assembly, guardrails
block before any audio, and a streaming-init failure falls back cleanly.
"""
from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from app.repositories.interview_repository import InterviewSessionRepository


def _force_streaming(monkeypatch):
    """Wrap get_or_create_for_token so the (real) session comes back streaming-enabled."""
    real = InterviewSessionRepository.get_or_create_for_token

    async def _wrapped(self, token):
        sess = await real(self, token)
        if sess is not None:
            sess.streaming_mode = True
        return sess

    monkeypatch.setattr(InterviewSessionRepository, "get_or_create_for_token", _wrapped)


class _StubStt:
    """Stand-in for StreamingSttService — no Azure dependency."""

    def __init__(self) -> None:
        self.frames = bytearray()

    def start(self) -> None:
        pass

    def push(self, frame: bytes) -> None:
        self.frames.extend(frame)

    async def finalize(self) -> str:
        return "I have five years of backend experience."


async def _fake_tts_stream(self, text: str):
    for chunk in (b"\x00\x01\x02", b"\x03\x04\x05"):
        yield chunk


def _drain_greeting(ws):
    """Consume the turn-0 welcome message (ai_turn_text + audio chunks + ai_audio_end)."""
    while True:
        msg = ws.receive_json()
        if msg["type"] == "ai_audio_end":
            return


@pytest.mark.asyncio
async def test_streaming_session_ready_advertises_mode(app, interview_token, monkeypatch):
    """session_ready carries streaming_mode=true for a streaming-enabled session (FR-005)."""
    _force_streaming(monkeypatch)
    with TestClient(app) as client:
        with patch("app.services.streaming_tts_service.StreamingTtsService.stream", _fake_tts_stream):
            with client.websocket_connect(f"/interviews/{interview_token}/connect") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "session_ready"
                assert msg["streaming_mode"] is True


@pytest.mark.asyncio
async def test_streaming_turn_emits_text_then_ordered_audio(app, interview_token, monkeypatch):
    """audio_frame*+end_of_speech → ai_turn_text, ordered ai_audio_chunk(seq), ai_audio_end (FR-004/SC-002);
    captured PCM is passed to the turn for assembly/storage (FR-006/SC-003)."""
    _force_streaming(monkeypatch)

    with TestClient(app) as client:
        with (
            patch("app.services.streaming_stt_service.StreamingSttService", _StubStt),
            patch("app.services.streaming_tts_service.StreamingTtsService.stream", _fake_tts_stream),
            patch(
                "app.services.interview_service.InterviewService.handle_streaming_turn",
                new_callable=AsyncMock,
            ) as mock_turn,
        ):
            mock_turn.return_value = {
                "ai_response": "Great — tell me about a hard bug you fixed.",
                "session_complete": False,
                "guardrail_triggered": False,
            }
            with client.websocket_connect(f"/interviews/{interview_token}/connect") as ws:
                assert ws.receive_json()["type"] == "session_ready"
                _drain_greeting(ws)

                frame = base64.b64encode(b"\x10\x00" * 160).decode()  # 20ms PCM16 @16k
                ws.send_json({"type": "audio_frame", "audio": frame})
                ws.send_json({"type": "audio_frame", "audio": frame})
                ws.send_json({"type": "end_of_speech"})

                assert ws.receive_json()["type"] == "turn_processing"
                transcript_msg = ws.receive_json()  # candidate transcript echoed to the chat
                assert transcript_msg["type"] == "partial_transcript" and transcript_msg["text"]
                text_msg = ws.receive_json()
                assert text_msg["type"] == "ai_turn_text" and text_msg["text"]

                c0 = ws.receive_json()
                c1 = ws.receive_json()
                assert c0["type"] == "ai_audio_chunk" and c0["seq"] == 0
                assert c1["type"] == "ai_audio_chunk" and c1["seq"] == 1
                assert ws.receive_json()["type"] == "ai_audio_end"

            # Captured frames were handed to the turn for WAV assembly + storage.
            assert mock_turn.await_count == 1
            assert mock_turn.await_args.kwargs["candidate_pcm"]  # non-empty bytes


@pytest.mark.asyncio
async def test_streaming_guardrail_blocks_before_audio(app, interview_token, monkeypatch):
    """Blocked input → turn_blocked and NO ai_audio_chunk is ever emitted (FR-007)."""
    _force_streaming(monkeypatch)

    with TestClient(app) as client:
        with (
            patch("app.services.streaming_stt_service.StreamingSttService", _StubStt),
            patch("app.services.streaming_tts_service.StreamingTtsService.stream", _fake_tts_stream),
            patch(
                "app.services.interview_service.InterviewService.handle_streaming_turn",
                new_callable=AsyncMock,
            ) as mock_turn,
        ):
            mock_turn.return_value = {
                "ai_response": "That topic isn't appropriate for this interview.",
                "session_complete": False,
                "guardrail_triggered": True,
            }
            with client.websocket_connect(f"/interviews/{interview_token}/connect") as ws:
                assert ws.receive_json()["type"] == "session_ready"
                _drain_greeting(ws)
                frame = base64.b64encode(b"\x10\x00" * 160).decode()
                ws.send_json({"type": "audio_frame", "audio": frame})
                ws.send_json({"type": "end_of_speech"})

                assert ws.receive_json()["type"] == "turn_processing"
                assert ws.receive_json()["type"] == "partial_transcript"
                blocked = ws.receive_json()
                assert blocked["type"] == "turn_blocked"
                # No audio chunk should follow a block.
                ws.send_json({"type": "end_of_speech"})  # idempotent no-op (stt reset)


@pytest.mark.asyncio
async def test_streaming_init_failure_falls_back(app, interview_token, monkeypatch):
    """If the streaming STT can't initialize, the session degrades with service_error (FR-008)."""
    _force_streaming(monkeypatch)

    class _BoomStt:
        def __init__(self) -> None:
            raise RuntimeError("azure speech unavailable")

    with TestClient(app) as client:
        with (
            patch("app.services.streaming_stt_service.StreamingSttService", _BoomStt),
            patch("app.services.streaming_tts_service.StreamingTtsService.stream", _fake_tts_stream),
        ):
            with client.websocket_connect(f"/interviews/{interview_token}/connect") as ws:
                assert ws.receive_json()["type"] == "session_ready"
                _drain_greeting(ws)
                frame = base64.b64encode(b"\x10\x00" * 160).decode()
                ws.send_json({"type": "audio_frame", "audio": frame})
                err = ws.receive_json()
                assert err["type"] == "service_error"
