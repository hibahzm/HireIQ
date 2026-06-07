from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.graphs.screening_graph import ScreeningState, screening_graph

logger = structlog.get_logger()

router = APIRouter(prefix="/agents", tags=["screening"])


class CvScreenRequest(BaseModel):
    application_id: str
    company_id: str
    cv_text: str
    job_criteria: dict[str, Any]
    hybrid_search_results: list[dict[str, Any]]


class CvScreenResponse(BaseModel):
    score: int
    rationale: str
    status: str
    guardrail_triggered: bool


@router.post("/cv-screen", response_model=CvScreenResponse)
async def cv_screen(body: CvScreenRequest) -> CvScreenResponse:
    structlog.contextvars.bind_contextvars(
        agent_type="cv_screening", application_id=body.application_id
    )

    initial_state: ScreeningState = {
        "application_id": body.application_id,
        "company_id": body.company_id,
        "cv_text": body.cv_text,
        "job_criteria": body.job_criteria,
        "hybrid_search_results": body.hybrid_search_results,
        "score": None,
        "rationale": None,
        "status": "pending",
        "guardrail_triggered": False,
    }

    result = await screening_graph.ainvoke(initial_state)

    return CvScreenResponse(
        score=result["score"] or 0,
        rationale=result["rationale"] or "",
        status=result["status"],
        guardrail_triggered=result["guardrail_triggered"],
    )
