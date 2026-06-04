from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.graphs.job_setup_graph import JobSetupState, job_setup_graph

logger = structlog.get_logger()

router = APIRouter(prefix="/agents/job-setup", tags=["job-setup"])


class JobSetupTurnRequest(BaseModel):
    job_id: str
    company_id: str
    conversation_history: list[dict[str, str]]
    user_message: str


class JobSetupTurnResponse(BaseModel):
    message: str
    status: str
    criteria_draft: dict[str, Any] | None = None


@router.post("/turn", response_model=JobSetupTurnResponse)
async def job_setup_turn(body: JobSetupTurnRequest) -> JobSetupTurnResponse:
    structlog.contextvars.bind_contextvars(agent_type="job_setup", job_id=body.job_id)

    # Append the new user message to history
    history = list(body.conversation_history)
    if body.user_message:
        history.append({"role": "user", "content": body.user_message})

    initial_state: JobSetupState = {
        "conversation_history": history,
        "criteria_draft": None,
        "status": "in_progress",
        "ai_message": "",
    }

    result = await job_setup_graph.ainvoke(initial_state)

    return JobSetupTurnResponse(
        message=result["ai_message"],
        status=result["status"],
        criteria_draft=result.get("criteria_draft"),
    )
