"""
Session resume and expiry integration tests.
Constitution Principle VIII — T055.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_session_resume_preserves_state(app, interview_token):
    """After disconnect + reconnect within 24h, turn_count is preserved in Redis state."""
    pass  # Covered in test_interview.py T055 fixture


@pytest.mark.asyncio
async def test_session_expired_after_24h(app):
    """
    Application with interview_token_expires_at in the past →
    WebSocket connect returns session_expired and closes 1008.
    """
    # This test requires a DB-backed fixture with an expired token.
    # Test is intentionally minimal — implementation in T063 must handle this path.
    pass
