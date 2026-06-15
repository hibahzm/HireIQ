from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.graphs.screening_graph import ScreeningState, screening_graph
from app.observability import get_langfuse_callbacks

logger = structlog.get_logger()

router = APIRouter(prefix="/agents", tags=["screening"])


class CvScreenRequest(BaseModel):
    application_id: str
    company_id: str
    cv_text: str
    job_description: str = ""
    job_criteria: dict[str, Any]


class CvScreenResponse(BaseModel):
    score: int
    rationale: str
    status: str
    guardrail_triggered: bool
    usage_events: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/cv-screen", response_model=CvScreenResponse)
async def cv_screen(body: CvScreenRequest) -> CvScreenResponse:
    structlog.contextvars.bind_contextvars(
        agent_type="cv_screening", application_id=body.application_id
    )

    initial_state: ScreeningState = {
        "application_id": body.application_id,
        "company_id": body.company_id,
        "cv_text": body.cv_text,
        "job_description": body.job_description,
        "job_criteria": body.job_criteria,
        "score": None,
        "rationale": None,
        "status": "pending",
        "guardrail_triggered": False,
        "usage_events": [],
    }

    result = await screening_graph.ainvoke(
        initial_state, config={"callbacks": get_langfuse_callbacks()}
    )

    return CvScreenResponse(
        score=result["score"] or 0,
        rationale=result["rationale"] or "",
        status=result["status"],
        guardrail_triggered=result["guardrail_triggered"],
        usage_events=result.get("usage_events", []),
    )
