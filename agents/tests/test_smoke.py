"""Smoke tests for the agents service.

Keeps `pytest tests/` from exiting 5 ("no tests collected") in CI, and gives a
fast import/wiring check that the FastAPI app builds and every agent route is
registered without needing OpenAI or any external service.
"""

import os

# Test mode → config skips Vault/Key Vault secret loading on import.
os.environ.setdefault("ENV", "test")


def test_app_imports_and_registers_agent_routes():
    from app.main import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/health" in paths
    for path in (
        "/agents/cv-screen",
        "/agents/evaluate",
        "/agents/interview/turn",
        "/agents/job-setup/turn",
    ):
        assert path in paths, f"missing agent route: {path}"


def test_langfuse_tracing_disabled_without_keys():
    from app.observability import get_langfuse_callbacks

    # No LANGFUSE_* configured in tests → tracing is a no-op (empty callbacks).
    assert get_langfuse_callbacks() == []
