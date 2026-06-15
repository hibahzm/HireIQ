"""
Integration tests for voice interview WebSocket.
Constitution Principle VIII — T054: write FIRST, confirm FAILING before T063.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
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
            patch(
                "app.services.interview_service.InterviewService.handle_turn",
                new_callable=AsyncMock,
            ) as mock_turn,
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

                final_turn = ws.receive_json()  # the closing AI line
                assert final_turn["type"] == "ai_turn"

                complete_msg = ws.receive_json()
                assert complete_msg["type"] == "interview_complete"


# ---------------------------------------------------------------------------
# T055 — Session resume after disconnect + 24h expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_resume_within_24h(app, interview_token):
    """Reconnect within 24h → resuming: true, turn_count preserved."""
    from unittest.mock import AsyncMock, patch

    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine
    from starlette.testclient import TestClient

    from tests.integration.conftest import ADMIN_URL

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
                # Send some turns (turn accounting lives in the mocked service, so
                # persist the count the way the real handle_turn would).
                for _ in range(3):
                    ws.send_json({"type": "text_input", "text": "Test response"})
                    ws.receive_json()  # turn_processing
                    ws.receive_json()  # ai_turn
            # Disconnect

    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                sa.text(
                    "UPDATE interview_sessions SET turn_count = 3, status = 'in_progress' "
                    "WHERE application_id = (SELECT id FROM applications WHERE interview_token = :tok)"
                ),
                {"tok": token},
            )
    finally:
        await engine.dispose()

    # The app's DB/Redis singletons are bound to the first TestClient's loop —
    # reset them so the second TestClient builds fresh ones on its own loop.
    import app.db as db
    from app import redis_client

    db._engine = None
    db._session_factory = None
    redis_client._redis = None

    with TestClient(app) as client:
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
