from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import _get_session_factory
from app.repositories.evaluation_repository import EvaluationRepository

logger = structlog.get_logger()

router = APIRouter(tags=["feedback"])


# ── Response schemas ─────────────────────────────────────────────────────────


class DimensionScorePublic(BaseModel):
    dimension: str
    score: int


class FeedbackSummary(BaseModel):
    strengths: str
    areas_for_improvement: str


class FeedbackReportResponse(BaseModel):
    job_title: str
    overall_score: int
    dimension_scores: list[DimensionScorePublic]
    summary: FeedbackSummary | None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_summary(raw: str | None) -> FeedbackSummary | None:
    if not raw:
        return None
    strengths = ""
    areas = ""
    for line in raw.splitlines():
        if line.lower().startswith("strengths:"):
            strengths = line[len("strengths:") :].strip()
        elif line.lower().startswith("areas for improvement:"):
            areas = line[len("areas for improvement:") :].strip()
    if not strengths and not areas:
        return FeedbackSummary(strengths=raw, areas_for_improvement="")
    return FeedbackSummary(strengths=strengths, areas_for_improvement=areas)


# ── Route ─────────────────────────────────────────────────────────────────────


@router.get("/feedback/{token}", response_model=FeedbackReportResponse)
async def get_feedback_report(token: str) -> FeedbackReportResponse:
    """
    Public — no auth required. Token is the authenticator.
    Returns 404 for unknown token, 410 for expired token.
    Deliberately excludes recommendation (hire/no-hire is internal).
    """
    async with _get_session_factory()() as session:
        async with session.begin():
            repo = EvaluationRepository(session)
            evaluation = await repo.get_by_feedback_token(token)

            if evaluation is None:
                # get_by_feedback_token applies the expiry filter, so a None result
                # is either an unknown token (404) or an expired one (410).
                # Re-look up without the expiry filter to tell them apart.
                row = await repo.get_feedback_token_row(token)
                if row is None:
                    raise HTTPException(status_code=404, detail="Feedback link not found")
                expires_at = row["feedback_token_expires_at"]
                if expires_at and expires_at < datetime.now(UTC):
                    raise HTTPException(status_code=410, detail="Feedback link has expired")
                raise HTTPException(status_code=404, detail="Feedback link not found")

            job_title = (
                await repo.get_job_title_by_application_id(evaluation.application_id)
                or "the position"
            )

    dimension_scores = [
        DimensionScorePublic(
            dimension=d.get("dimension", ""),
            score=int(d.get("score", 0)),
        )
        for d in (evaluation.dimension_scores or [])
    ]

    return FeedbackReportResponse(
        job_title=job_title,
        overall_score=evaluation.overall_score,
        dimension_scores=dimension_scores,
        summary=_parse_summary(evaluation.summary),
    )
