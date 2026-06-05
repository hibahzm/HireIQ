from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import sqlalchemy as sa
from app.api.deps import get_authed_session, require_recruiter_or_admin
from app.models.user import User
from app.repositories.evaluation_repository import EvaluationRepository
from app.services.storage_service import StorageService

logger = structlog.get_logger()

router = APIRouter(tags=["evaluations"])


# ── Response schemas ─────────────────────────────────────────────────────────

class CandidateSummary(BaseModel):
    full_name: str


class ShortlistItem(BaseModel):
    evaluation_id: str
    application_id: str
    candidate: CandidateSummary
    overall_score: int
    recommendation: str
    confidence_flag: bool
    created_at: datetime


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


class TranscriptTurn(BaseModel):
    turn_index: int
    speaker: str
    content_text: str
    audio_url: str | None


class EvaluationDetailResponse(BaseModel):
    id: str
    application_id: str
    overall_score: int
    recommendation: str
    dimension_scores: list[DimensionScore]
    consistency_flags: list[ConsistencyFlag]
    communication_quality: CommunicationQuality
    confidence_flag: bool
    confidence_reason: str | None
    summary: str | None
    transcript: list[TranscriptTurn]
    created_at: datetime


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/evaluations", response_model=list[ShortlistItem])
async def list_evaluations(
    job_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
) -> list[ShortlistItem]:
    rows = await EvaluationRepository(session).list_by_job_ranked(job_id)
    return [
        ShortlistItem(
            evaluation_id=str(r["evaluation_id"]),
            application_id=str(r["application_id"]),
            candidate=CandidateSummary(full_name=r["full_name"]),
            overall_score=r["overall_score"],
            recommendation=r["recommendation"],
            confidence_flag=r["confidence_flag"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationDetailResponse)
async def get_evaluation(
    evaluation_id: str,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
) -> EvaluationDetailResponse:
    repo = EvaluationRepository(session)
    evaluation = await repo.get_by_id(evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Fetch transcript with audio URLs
    result = await session.execute(
        sa.text(
            """
            SELECT im.turn_index, im.speaker, im.content_text, im.audio_blob_key
            FROM interview_messages im
            JOIN interview_sessions s ON s.id = im.session_id
            JOIN applications a ON a.id = s.application_id
            WHERE a.id = :application_id
            ORDER BY im.turn_index
            """
        ),
        {"application_id": evaluation.application_id},
    )
    rows = result.mappings().all()

    transcript = [
        TranscriptTurn(
            turn_index=r["turn_index"],
            speaker=r["speaker"],
            content_text=r["content_text"],
            audio_url=(
                f"/evaluations/{evaluation_id}/transcript/{r['turn_index']}/audio"
                if r["audio_blob_key"]
                else None
            ),
        )
        for r in rows
    ]

    comm = evaluation.communication_quality or {}
    return EvaluationDetailResponse(
        id=evaluation.id,
        application_id=evaluation.application_id,
        overall_score=evaluation.overall_score,
        recommendation=evaluation.recommendation,
        dimension_scores=[DimensionScore(**d) for d in (evaluation.dimension_scores or [])],
        consistency_flags=[ConsistencyFlag(**f) for f in (evaluation.consistency_flags or [])],
        communication_quality=CommunicationQuality(
            response_depth=comm.get("response_depth", 0.5),
            filler_word_frequency=comm.get("filler_word_frequency", 0.0),
            deflection_frequency=comm.get("deflection_frequency", 0.0),
        ),
        confidence_flag=evaluation.confidence_flag,
        confidence_reason=evaluation.confidence_reason,
        summary=evaluation.summary,
        transcript=transcript,
        created_at=evaluation.created_at,
    )


@router.get("/evaluations/{evaluation_id}/transcript/{turn_index}/audio")
async def get_turn_audio(
    evaluation_id: str,
    turn_index: int,
    current_user: User = Depends(require_recruiter_or_admin),
    session: AsyncSession = Depends(get_authed_session),
) -> StreamingResponse:
    # Verify the evaluation belongs to this tenant
    evaluation = await EvaluationRepository(session).get_by_id(evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    result = await session.execute(
        sa.text(
            """
            SELECT im.audio_blob_key
            FROM interview_messages im
            JOIN interview_sessions s ON s.id = im.session_id
            JOIN applications a ON a.id = s.application_id
            WHERE a.id = :application_id
              AND im.turn_index = :turn_index
            LIMIT 1
            """
        ),
        {"application_id": evaluation.application_id, "turn_index": turn_index},
    )
    row = result.mappings().first()
    if not row or not row["audio_blob_key"]:
        raise HTTPException(status_code=404, detail="No audio for this turn")

    audio_bytes = await StorageService().fetch(row["audio_blob_key"])
    if audio_bytes is None:
        raise HTTPException(status_code=404, detail="Audio not found in storage")

    return StreamingResponse(
        iter([audio_bytes]),
        media_type="audio/mpeg",
    )
