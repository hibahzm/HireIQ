from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_usage_event import LlmUsageEvent


class LlmUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        company_id: str | None,
        agent_type: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        estimated_cost_usd: Decimal = Decimal("0"),
        metadata: dict[str, Any] | None = None,
    ) -> LlmUsageEvent:
        event = LlmUsageEvent(
            company_id=company_id,
            agent_type=agent_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=estimated_cost_usd,
            metadata_json=metadata or {},
        )
        self._session.add(event)
        await self._session.flush()
        return event
