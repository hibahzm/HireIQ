"""
Integration tests for the evaluation pipeline.
Constitution Principle VIII — write FIRST, confirm FAILING before T073.

T067: triggered by InterviewService on session_complete → assert full
evaluation payload (overall_score, dimension_scores with evidence_quotes,
consistency_flags, communication_quality, confidence_flag) is persisted
and PII-redacted.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _agents_response(payload: dict) -> MagicMock:
    """httpx-like response: sync .json()/.raise_for_status() (AsyncMock would
    make .json() a coroutine and break `resp.json().get(...)`)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


@pytest.mark.asyncio
async def test_evaluation_pipeline_persists_full_payload(app, completed_interview_session):
    """
    Trigger evaluation from a completed interview session.
    Asserts:
    - overall_score is set (0–100)
    - dimension_scores is a non-empty list; each item has evidence_quotes
    - consistency_flags is a list (may be empty)
    - communication_quality has required fields
    - confidence_flag is a bool
    - all text fields are PII-redacted (no raw email addresses)
    - application status updated to 'evaluated'
    """
    session_id, company_id, application_id = completed_interview_session

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_agents:
        mock_agents.return_value = _agents_response(
            {
                "overall_score": 74,
                "recommendation": "hire",
                "dimension_scores": [
                    {
                        "dimension": "technical_skills",
                        "score": 80,
                        "evidence_quotes": ["Candidate described async/await usage in Python."],
                    }
                ],
                "consistency_flags": [],
                "communication_quality": {
                    "response_depth": 0.7,
                    "filler_word_frequency": 0.05,
                    "deflection_frequency": 0.0,
                },
                "confidence_flag": False,
                "confidence_reason": None,
            }
        )

        import sqlalchemy as sa

        from app.db import _get_session_factory

        async with _get_session_factory()() as session:
            async with session.begin():
                await session.execute(
                    sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                    {"cid": company_id},
                )
                from app.redis_client import _redis
                from app.services.evaluation_service import EvaluationService

                svc = EvaluationService(session, _redis)
                await svc.evaluate_from_session(session_id=session_id, company_id=company_id)

        # Verify evaluation row was persisted
        async with _get_session_factory()() as session:
            async with session.begin():
                await session.execute(
                    sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                    {"cid": company_id},
                )
                result = await session.execute(
                    sa.text("SELECT * FROM evaluations WHERE application_id = :app_id"),
                    {"app_id": application_id},
                )
                row = result.mappings().first()

    assert row is not None, "Evaluation row must be created"
    assert 0 <= row["overall_score"] <= 100
    assert row["recommendation"] in ("hire", "no_hire", "uncertain")

    dim_scores = row["dimension_scores"]
    assert isinstance(dim_scores, list) and len(dim_scores) > 0
    for dim in dim_scores:
        assert "evidence_quotes" in dim, "Each dimension must have evidence_quotes"

    assert isinstance(row["consistency_flags"], list)
    assert "response_depth" in row["communication_quality"]
    assert isinstance(row["confidence_flag"], bool)

    # PII check: no raw email addresses in any text field
    for field in ("dimension_scores", "consistency_flags"):
        assert "@" not in str(row[field]) or "[EMAIL]" in str(row[field]), f"PII found in {field}"

    # Application status must be updated
    async with _get_session_factory()() as session:
        async with session.begin():
            await session.execute(
                sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                {"cid": company_id},
            )
            app_row = await session.execute(
                sa.text("SELECT status FROM applications WHERE id = :id"),
                {"id": application_id},
            )
            app_status = app_row.scalar_one()

    assert app_status == "evaluated"


@pytest.mark.asyncio
async def test_evaluation_confidence_flag_set_for_shallow_responses(
    app, completed_interview_session
):
    """
    When avg evidence_quotes per dimension < 1 OR turn depth < 0.3,
    confidence_flag must be True.
    """
    session_id, company_id, application_id = completed_interview_session

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_agents:
        mock_agents.return_value = _agents_response(
            {
                "overall_score": 30,
                "recommendation": "no_hire",
                "dimension_scores": [
                    {"dimension": "communication", "score": 25, "evidence_quotes": []},
                ],
                "consistency_flags": [],
                "communication_quality": {
                    "response_depth": 0.1,
                    "filler_word_frequency": 0.5,
                    "deflection_frequency": 0.4,
                },
                "confidence_flag": True,
                "confidence_reason": "Insufficient evidence — candidate gave one-word answers.",
            }
        )

        import sqlalchemy as sa

        from app.db import _get_session_factory

        async with _get_session_factory()() as session:
            async with session.begin():
                await session.execute(
                    sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                    {"cid": company_id},
                )
                from app.redis_client import _redis
                from app.services.evaluation_service import EvaluationService

                svc = EvaluationService(session, _redis)
                await svc.evaluate_from_session(session_id=session_id, company_id=company_id)

        async with _get_session_factory()() as session:
            async with session.begin():
                await session.execute(
                    sa.text("SELECT set_config('app.current_company_id', :cid, true)"),
                    {"cid": company_id},
                )
                result = await session.execute(
                    sa.text(
                        "SELECT confidence_flag, confidence_reason "
                        "FROM evaluations WHERE application_id = :app_id"
                    ),
                    {"app_id": application_id},
                )
                row = result.mappings().first()

    assert row["confidence_flag"] is True
    assert row["confidence_reason"] is not None and len(row["confidence_reason"]) > 0
