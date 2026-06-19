from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import get_settings
from app.services.notification_service import NotificationService


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        self.set_calls.append((key, value, ex))


def _resend_settings() -> SimpleNamespace:
    return SimpleNamespace(
        EMAIL_BACKEND="resend",
        EMAIL_API_KEY="test-key",
        EMAIL_FROM="noreply@example.com",
        INTERVIEW_LINK_EXPIRY_HOURS=48,
    )


def _service(redis: FakeRedis, monkeypatch: pytest.MonkeyPatch) -> NotificationService:
    monkeypatch.setenv("ENV", "test")
    get_settings.cache_clear()
    service = NotificationService(redis)
    service._settings = _resend_settings()
    return service


@pytest.mark.asyncio
async def test_resend_failure_does_not_raise_or_mark_dedup(monkeypatch: pytest.MonkeyPatch):
    redis = FakeRedis()
    service = _service(redis, monkeypatch)
    service._send_resend = AsyncMock(side_effect=RuntimeError("Resend test mode"))  # type: ignore[method-assign]

    await service.send_sourcing_invitation_email(
        candidate_email="candidate@example.com",
        company_name="Acme",
        job_title="Backend Engineer",
        link="http://localhost:3000/candidate",
    )

    service._send_resend.assert_awaited_once()
    assert redis.set_calls == []


@pytest.mark.asyncio
async def test_successful_resend_marks_dedup(monkeypatch: pytest.MonkeyPatch):
    redis = FakeRedis()
    service = _service(redis, monkeypatch)
    service._send_resend = AsyncMock(return_value=None)  # type: ignore[method-assign]

    await service.send_sourcing_invitation_email(
        candidate_email="candidate@example.com",
        company_name="Acme",
        job_title="Backend Engineer",
        link="http://localhost:3000/candidate",
    )

    assert len(redis.set_calls) == 1
    key, value, ttl = redis.set_calls[0]
    assert key.startswith("email:dedup:sourcing_invitation:")
    assert value == "1"
    assert ttl == 86400
