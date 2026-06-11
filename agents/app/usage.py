from __future__ import annotations

from decimal import Decimal
from typing import Any

_TOKEN_PRICING_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
}


def _pricing_key(model: str) -> str:
    for key in _TOKEN_PRICING_PER_MILLION:
        if model.startswith(key):
            return key
    return model


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    input_price, output_price = _TOKEN_PRICING_PER_MILLION.get(
        _pricing_key(model),
        (Decimal("0"), Decimal("0")),
    )
    cost = (
        (Decimal(max(prompt_tokens, 0)) * input_price)
        + (Decimal(max(completion_tokens, 0)) * output_price)
    ) / Decimal(1_000_000)
    return float(cost.quantize(Decimal("0.000001")))


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if isinstance(value, str | int | float | bool) or value is None:
            safe[str(key)] = value
    return safe


def usage_event_from_response(
    response: Any,
    *,
    company_id: str | None,
    agent_type: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    usage_metadata = getattr(response, "usage_metadata", None) or {}
    response_metadata = getattr(response, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or {}

    prompt_tokens = int(
        usage_metadata.get("input_tokens")
        or token_usage.get("prompt_tokens")
        or token_usage.get("input_tokens")
        or 0
    )
    completion_tokens = int(
        usage_metadata.get("output_tokens")
        or token_usage.get("completion_tokens")
        or token_usage.get("output_tokens")
        or 0
    )
    if prompt_tokens == 0 and completion_tokens == 0:
        return None

    model = str(
        response_metadata.get("model_name")
        or response_metadata.get("model")
        or usage_metadata.get("model_name")
        or "unknown"
    )

    return {
        "company_id": company_id,
        "agent_type": agent_type,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "estimated_cost_usd": _estimate_cost(model, prompt_tokens, completion_tokens),
        "metadata": _safe_metadata(metadata),
    }


def append_usage_event(
    state: dict[str, Any],
    response: Any,
    *,
    agent_type: str,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    events = list(state.get("usage_events") or [])
    event = usage_event_from_response(
        response,
        company_id=state.get("company_id"),
        agent_type=agent_type,
        metadata=metadata,
    )
    if event:
        events.append(event)
    return events
