from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.graphs.interview_graph import InterviewState, interview_graph
from app.observability import get_langfuse_callbacks

logger = structlog.get_logger()

router = APIRouter(prefix="/agents/interview", tags=["interview"])


class InterviewTurnRequest(BaseModel):
    company_id: str | None = None
    session_id: str | None = None
    conversation_history: list[dict[str, str]]
    dimensions_covered: list[str]
    dimensions_remaining: list[str]
    turn_count: int
    max_turns: int
    job_criteria: dict[str, Any]
    company_overview: str | None = None
    candidate_cv: str | None = None


class InterviewTurnResponse(BaseModel):
    ai_response: str
    updated_state: dict[str, Any]
    session_complete: bool
    dimensions_remaining: list[str]
    guardrail_triggered: bool
    blocked_redirect: str | None
    usage_events: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/turn", response_model=InterviewTurnResponse)
async def interview_turn(body: InterviewTurnRequest) -> InterviewTurnResponse:
    structlog.contextvars.bind_contextvars(agent_type="interview")

    initial_state: InterviewState = {
        "company_id": body.company_id or "",
        "session_id": body.session_id,
        "conversation_history": body.conversation_history,
        "dimensions_covered": body.dimensions_covered,
        "dimensions_remaining": body.dimensions_remaining,
        "turn_count": body.turn_count,
        "max_turns": body.max_turns,
        "job_criteria": body.job_criteria,
        "company_overview": body.company_overview,
        "candidate_cv": body.candidate_cv,
        "ai_response": "",
        "session_complete": False,
        "guardrail_triggered": False,
        "blocked_redirect": None,
        "usage_events": [],
    }

    result = await interview_graph.ainvoke(
        initial_state, config={"callbacks": get_langfuse_callbacks()}
    )

    return InterviewTurnResponse(
        ai_response=result["ai_response"],
        updated_state={
            "dimensions_covered": result["dimensions_covered"],
            "dimensions_remaining": result["dimensions_remaining"],
            "turn_count": result["turn_count"],
        },
        session_complete=result["session_complete"],
        dimensions_remaining=result["dimensions_remaining"],
        guardrail_triggered=result["guardrail_triggered"],
        blocked_redirect=result.get("blocked_redirect"),
        usage_events=result.get("usage_events", []),
    )
