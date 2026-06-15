"""Nodes for the CV-screening agent graph.

Graph wiring lives in ``app.graphs.screening_graph``.
"""

from __future__ import annotations

from typing import Any, TypedDict

import structlog
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from app.graphs.json_utils import parse_json_object
from app.guardrails import PIIRedactor, registry
from app.prompts import SCREENING_SYSTEM
from app.usage import append_usage_event

logger = structlog.get_logger()


class ScreeningState(TypedDict):
    application_id: str
    company_id: str
    cv_text: str
    job_description: str
    job_criteria: dict[str, Any]
    score: int | None
    rationale: str | None
    status: str
    guardrail_triggered: bool
    usage_events: list[dict[str, Any]]


def _build_llm() -> ChatOpenAI:
    from app.config import get_settings
    settings = get_settings()
    return ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.OPENAI_API_KEY,
        temperature=0.1,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


async def score_cv(state: ScreeningState) -> ScreeningState:
    if not registry.check_input(state["cv_text"]).passed:
        logger.warning("screening.guardrail_triggered", application_id=state["application_id"])
        return {
            **state,
            "score": 0,
            "rationale": "Content blocked by guardrails.",
            "status": "rejected",
            "guardrail_triggered": True,
        }

    prompt = SCREENING_SYSTEM.format(
        job_description=(state.get("job_description") or "").strip() or "(no description provided)",
        criteria=str(state["job_criteria"]),
        cv_text=state["cv_text"],
    )

    response = await _build_llm().ainvoke([SystemMessage(content=prompt)])
    usage_events = append_usage_event(
        state,
        response,
        agent_type="cv_screening",
        metadata={"application_id": state["application_id"]},
    )
    raw = response.content

    if not registry.check_output(raw).passed:
        return {
            **state,
            "score": 0,
            "rationale": "Output blocked by guardrails.",
            "status": "rejected",
            "guardrail_triggered": True,
            "usage_events": usage_events,
        }

    data = parse_json_object(raw)
    try:
        if data is None:
            raise ValueError("unparseable screening response")
        score = int(data["score"])
        rationale = PIIRedactor.redact(str(data["rationale"]))
        threshold = state["job_criteria"].get("min_screening_score", 70)
        status = "qualified" if score >= threshold else "rejected"
    except (KeyError, TypeError, ValueError):
        # Surface as an error so the backend marks screening "failed" (re-runnable)
        # instead of silently rejecting the candidate on a malformed LLM response.
        logger.warning("screening.unparseable_response", application_id=state["application_id"])
        score = 0
        rationale = "The screening model returned an unparseable response. Re-run screening."
        status = "error"

    return {
        **state,
        "score": score,
        "rationale": rationale,
        "status": status,
        "guardrail_triggered": False,
        "usage_events": usage_events,
    }
