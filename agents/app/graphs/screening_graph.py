from __future__ import annotations

from typing import Any, TypedDict

import structlog
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.guardrails import PIIRedactor, registry

logger = structlog.get_logger()

_SCREENING_PROMPT = """You are an expert hiring assistant evaluating a candidate's CV against job criteria.

Job criteria:
{criteria}

Hybrid search results (most relevant CV sections):
{search_results}

CV text:
{cv_text}

Score this candidate from 0-100 based on how well they meet the criteria.
Provide:
1. A numeric score (integer, 0-100)
2. A concise rationale (2-3 sentences)
3. Qualification status: "qualified" (score >= threshold) or "rejected"

Respond ONLY with valid JSON:
{{"score": <int>, "rationale": "<string>", "status": "qualified" | "rejected"}}

Important: Do NOT include any personal identifying information (names, emails, phone numbers) in the rationale."""


class ScreeningState(TypedDict):
    application_id: str
    company_id: str
    cv_text: str
    job_criteria: dict[str, Any]
    hybrid_search_results: list[dict[str, Any]]
    score: int | None
    rationale: str | None
    status: str
    guardrail_triggered: bool


def _build_llm() -> ChatOpenAI:
    from app.config import get_settings
    settings = get_settings()
    return ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0.1)


async def score_cv(state: ScreeningState) -> ScreeningState:
    guard_result = registry.check_input(state["cv_text"])
    if not guard_result.passed:
        logger.warning("screening.guardrail_triggered", application_id=state["application_id"])
        return {
            **state,
            "score": 0,
            "rationale": "Content blocked by guardrails.",
            "status": "rejected",
            "guardrail_triggered": True,
        }

    search_summary = "\n".join(
        f"- {r.get('chunk_text', '')[:200]}" for r in state["hybrid_search_results"][:5]
    )
    criteria_text = str(state["job_criteria"])

    prompt = _SCREENING_PROMPT.format(
        criteria=criteria_text,
        search_results=search_summary,
        cv_text=state["cv_text"][:3000],
    )

    llm = _build_llm()
    response = await llm.ainvoke([SystemMessage(content=prompt)])
    raw = response.content

    output_guard = registry.check_output(raw)
    if not output_guard.passed:
        return {
            **state,
            "score": 0,
            "rationale": "Output blocked by guardrails.",
            "status": "rejected",
            "guardrail_triggered": True,
        }

    import json
    try:
        data = json.loads(raw)
        score = int(data["score"])
        rationale = PIIRedactor.redact(str(data["rationale"]))
        threshold = state["job_criteria"].get("min_screening_score", 70)
        status = "qualified" if score >= threshold else "rejected"
    except (json.JSONDecodeError, KeyError, ValueError):
        score = 0
        rationale = "Unable to parse evaluation result."
        status = "rejected"

    return {
        **state,
        "score": score,
        "rationale": rationale,
        "status": status,
        "guardrail_triggered": False,
    }


def build_screening_graph() -> StateGraph:
    graph = StateGraph(ScreeningState)
    graph.add_node("score_cv", score_cv)
    graph.set_entry_point("score_cv")
    graph.add_edge("score_cv", END)
    return graph.compile()


screening_graph = build_screening_graph()
