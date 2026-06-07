from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.graphs.evaluation_graph import EvaluationState, evaluation_graph

logger = structlog.get_logger()

router = APIRouter(prefix="/agents", tags=["evaluation"])


class TranscriptTurn(BaseModel):
    turn_index: int
    speaker: str
    content_text: str


class EvaluateRequest(BaseModel):
    application_id: str
    company_id: str
    cv_text: str
    job_criteria: dict[str, Any]
    transcript: list[TranscriptTurn]


class DimensionScore(BaseModel):
    dimension: str
    score: int
    evidence_quotes: list[str]


class ConsistencyFlag(BaseModel):
    claim: str
    cv_statement: str
    interview_statement: str
    flag_type: str


class CommunicationQuality(BaseModel):
    response_depth: float
    filler_word_frequency: float
    deflection_frequency: float


class FeedbackSummary(BaseModel):
    strengths: str
    areas_for_improvement: str


class EvaluateResponse(BaseModel):
    overall_score: int
    recommendation: str
    dimension_scores: list[DimensionScore]
    consistency_flags: list[ConsistencyFlag]
    communication_quality: CommunicationQuality
    confidence_flag: bool
    confidence_reason: str | None
    feedback_summary: FeedbackSummary | None


def _parse_summary(raw: str | None) -> FeedbackSummary | None:
    if not raw:
        return None
    strengths = ""
    areas = ""
    for line in raw.splitlines():
        if line.lower().startswith("strengths:"):
            strengths = line[len("strengths:"):].strip()
        elif line.lower().startswith("areas for improvement:"):
            areas = line[len("areas for improvement:"):].strip()
    if not strengths and not areas:
        return FeedbackSummary(strengths=raw, areas_for_improvement="")
    return FeedbackSummary(strengths=strengths, areas_for_improvement=areas)


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(body: EvaluateRequest) -> EvaluateResponse:
    structlog.contextvars.bind_contextvars(
        agent_type="evaluation", application_id=body.application_id
    )

    transcript_dicts = [t.model_dump() for t in body.transcript]

    initial_state: EvaluationState = {
        "application_id": body.application_id,
        "company_id": body.company_id,
        "cv_text": body.cv_text,
        "job_criteria": body.job_criteria,
        "transcript": transcript_dicts,
        "dimension_scores": [],
        "consistency_flags": [],
        "communication_quality": {},
        "overall_score": 0,
        "recommendation": "uncertain",
        "confidence_flag": False,
        "confidence_reason": None,
        "summary": None,
        "guardrail_triggered": False,
    }

    result = await evaluation_graph.ainvoke(initial_state)

    comm = result.get("communication_quality") or {}
    return EvaluateResponse(
        overall_score=result.get("overall_score", 0),
        recommendation=result.get("recommendation", "uncertain"),
        dimension_scores=[DimensionScore(**d) for d in result.get("dimension_scores", [])],
        consistency_flags=[ConsistencyFlag(**f) for f in result.get("consistency_flags", [])],
        communication_quality=CommunicationQuality(
            response_depth=comm.get("response_depth", 0.5),
            filler_word_frequency=comm.get("filler_word_frequency", 0.0),
            deflection_frequency=comm.get("deflection_frequency", 0.0),
        ),
        confidence_flag=result.get("confidence_flag", False),
        confidence_reason=result.get("confidence_reason"),
        feedback_summary=_parse_summary(result.get("summary")),
    )
