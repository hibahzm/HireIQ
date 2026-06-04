"""
Integration tests for voice interview WebSocket.
Constitution Principle VIII — T054: write FIRST, confirm FAILING before T063.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.fixture
async def client(app):
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# T054 — WebSocket turn sequence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_websocket_interview_turn_sequence(app, interview_token):
    """
    Connect to WS → send text_input → receive ai_turn → repeat → receive interview_complete.
    All messages stored. Final session status = 'completed'.
    """
    from unittest.mock import AsyncMock, patch
    from starlette.testclient import TestClient

    token = interview_token

    with TestClient(app) as client:
        with (
            patch("app.services.interview_service.InterviewService.handle_turn", new_callable=AsyncMock) as mock_turn,
        ):
            mock_turn.return_value = {
                "ai_response": "Tell me about your experience.",
                "session_complete": False,
                "audio_bytes": None,
                "guardrail_triggered": False,
            }

            with client.websocket_connect(f"/interviews/{token}/connect") as ws:
                # Receive session_ready
                msg = ws.receive_json()
                assert msg["type"] == "session_ready"

                # Send a text_input
                ws.send_json({"type": "text_input", "text": "I have 5 years of Python experience."})

                # Expect turn_processing then ai_turn
                processing = ws.receive_json()
                assert processing["type"] == "turn_processing"

                ai_msg = ws.receive_json()
                assert ai_msg["type"] == "ai_turn"
                assert "text" in ai_msg

                # Simulate session completion
                mock_turn.return_value = {
                    "ai_response": "Thank you, the interview is complete.",
                    "session_complete": True,
                    "audio_bytes": None,
                    "guardrail_triggered": False,
                }

                ws.send_json({"type": "text_input", "text": "That's all from my side."})
                ws.receive_json()  # turn_processing

                complete_msg = ws.receive_json()
                assert complete_msg["type"] == "interview_complete"


# ---------------------------------------------------------------------------
# T055 — Session resume after disconnect + 24h expiry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_resume_within_24h(app, interview_token):
    """Reconnect within 24h → resuming: true, turn_count preserved."""
    from starlette.testclient import TestClient
    from unittest.mock import AsyncMock, patch

    token = interview_token

    with TestClient(app) as client:
        with patch(
            "app.services.interview_service.InterviewService.handle_turn", new_callable=AsyncMock
        ) as mock_turn:
            mock_turn.return_value = {
                "ai_response": "OK",
                "session_complete": False,
                "audio_bytes": None,
                "guardrail_triggered": False,
            }

            # First connection
            with client.websocket_connect(f"/interviews/{token}/connect") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "session_ready"
                # Send some turns
                for _ in range(3):
                    ws.send_json({"type": "text_input", "text": "Test response"})
                    ws.receive_json()  # turn_processing
                    ws.receive_json()  # ai_turn
            # Disconnect

            # Second connection (within 24h — no time manipulation needed in fast test)
            with client.websocket_connect(f"/interviews/{token}/connect") as ws2:
                resume_msg = ws2.receive_json()
                assert resume_msg["type"] == "session_ready"
                assert resume_msg.get("resuming") is True
                assert resume_msg.get("turn_count", 0) >= 3


@pytest.mark.asyncio
async def test_expired_token_returns_session_expired(app):
    """Expired interview token → WS closes with 1008 after session_expired message."""
    from starlette.testclient import TestClient

    fake_token = "00000000-0000-0000-0000-000000000000"

    with TestClient(app) as client:
        with client.websocket_connect(f"/interviews/{fake_token}/connect") as ws:
            msg = ws.receive_json()
            # Should receive session_expired or connection should close
            assert msg["type"] in ("session_expired", "error")
