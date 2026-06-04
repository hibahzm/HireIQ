from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.graphs.interview_graph import InterviewState, interview_graph

logger = structlog.get_logger()

router = APIRouter(prefix="/agents/interview", tags=["interview"])


class InterviewTurnRequest(BaseModel):
    conversation_history: list[dict[str, str]]
    dimensions_covered: list[str]
    dimensions_remaining: list[str]
    turn_count: int
    max_turns: int
    job_criteria: dict[str, Any]


class InterviewTurnResponse(BaseModel):
    ai_response: str
    updated_state: dict[str, Any]
    session_complete: bool
    dimensions_remaining: list[str]
    guardrail_triggered: bool
    blocked_redirect: str | None


@router.post("/turn", response_model=InterviewTurnResponse)
async def interview_turn(body: InterviewTurnRequest) -> InterviewTurnResponse:
    structlog.contextvars.bind_contextvars(agent_type="interview")

    initial_state: InterviewState = {
        "conversation_history": body.conversation_history,
        "dimensions_covered": body.dimensions_covered,
        "dimensions_remaining": body.dimensions_remaining,
        "turn_count": body.turn_count,
        "max_turns": body.max_turns,
        "job_criteria": body.job_criteria,
        "ai_response": "",
        "session_complete": False,
        "guardrail_triggered": False,
        "blocked_redirect": None,
    }

    result = await interview_graph.ainvoke(initial_state)

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
    )
