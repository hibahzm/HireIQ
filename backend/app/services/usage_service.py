from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.llm_usage_repository import LlmUsageRepository

# Static estimates per 1M units. They are operational estimates for dashboards,
# not billing authority; update them when vendor pricing changes.
_TOKEN_PRICING_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "text-embedding-3-small": (Decimal("0.02"), Decimal("0")),
}


def _pricing_key(model: str) -> str:
    for key in _TOKEN_PRICING_PER_MILLION:
        if model.startswith(key):
            return key
    return model


def estimate_usage_cost(
    *,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> Decimal:
    input_price, output_price = _TOKEN_PRICING_PER_MILLION.get(
        _pricing_key(model),
        (Decimal("0"), Decimal("0")),
    )
    cost = (
        (Decimal(max(prompt_tokens, 0)) * input_price)
        + (Decimal(max(completion_tokens, 0)) * output_price)
    ) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))


def _int_value(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.000001"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _safe_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, str | int | float | bool) or value is None:
            safe[str(key)] = value
    return safe


async def record_usage_events(
    session: AsyncSession,
    *,
    company_id: str | None,
    events: list[dict[str, Any]] | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not events:
        return

    repo = LlmUsageRepository(session)
    base_metadata = _safe_metadata(metadata)
    for event in events:
        if not isinstance(event, dict):
            continue
        model = str(event.get("model") or "unknown")
        prompt_tokens = _int_value(event.get("prompt_tokens"))
        completion_tokens = _int_value(event.get("completion_tokens"))
        estimated_cost = _decimal_value(event.get("estimated_cost_usd"))
        if estimated_cost == 0:
            estimated_cost = estimate_usage_cost(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        event_metadata = {
            **base_metadata,
            **_safe_metadata(event.get("metadata")),
            "pricing_basis": "static_estimate",
        }
        event_company_id = event.get("company_id") or company_id
        await repo.create(
            company_id=str(event_company_id) if event_company_id else None,
            agent_type=str(event.get("agent_type") or "unknown"),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=estimated_cost,
            metadata=event_metadata,
        )
