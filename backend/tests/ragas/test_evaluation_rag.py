"""
T084b — RAGAS quality gate for the evaluation pipeline.

Calls the real agents `/agents/evaluate` endpoint over HTTP for each golden
transcript. The candidate turns are the retrieved context; the evaluation's
per-dimension evidence quotes + summary are the answer. RAGAS scores whether the
evidence/summary is grounded in what the candidate actually said (faithfulness)
and whether the cited turns are relevant to each dimension (context precision).

Skipped unless a real OPENAI_API_KEY is present and the agents service is
reachable (RAGAS uses an LLM judge).
"""
from __future__ import annotations

import uuid

import httpx
import pytest

from tests.ragas.conftest import (
    AGENTS_BASE_URL,
    CONTEXT_PRECISION_THRESHOLD,
    FAITHFULNESS_THRESHOLD,
    agents_headers,
    load_transcript_fixtures,
    log_ragas_run,
    requires_ragas,
)


@requires_ragas
@pytest.mark.asyncio
async def test_evaluation_rag_faithfulness_and_precision():
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import context_precision, faithfulness

    fixtures = load_transcript_fixtures()
    assert len(fixtures) == 5, "Golden set must contain 5 transcript samples"

    questions, answers, contexts, references = [], [], [], []

    async with httpx.AsyncClient(base_url=AGENTS_BASE_URL, timeout=120) as client:
        for fx in fixtures:
            criteria = fx["job_criteria"]
            turns = [t["content_text"] for t in fx["transcript"] if t["speaker"] == "candidate"]
            resp = await client.post(
                "/agents/evaluate",
                headers=agents_headers(),
                json={
                    "application_id": str(uuid.uuid4()),
                    "company_id": str(uuid.uuid4()),
                    "cv_text": fx["cv_text"],
                    "job_criteria": criteria,
                    "transcript": fx["transcript"],
                },
            )
            resp.raise_for_status()
            body = resp.json()

            evidence: list[str] = []
            for dim in body.get("dimension_scores", []):
                evidence.extend(dim.get("evidence_quotes", []))
            summary = body.get("summary") or {}
            summary_text = " ".join(
                v for v in (summary.values() if isinstance(summary, dict) else []) if v
            )
            answer = (" ".join(evidence) + " " + summary_text).strip()

            questions.append(
                f"Assess this candidate against {', '.join(criteria['evaluation_dimensions'])}."
            )
            answers.append(answer)
            contexts.append(turns)
            references.append(" ".join(fx["ground_truth_evidence"].values()))

    ds = Dataset.from_dict(
        {"question": questions, "answer": answers, "contexts": contexts, "reference": references}
    )

    scores = evaluate(ds, metrics=[faithfulness, context_precision])
    faith = float(scores["faithfulness"])
    prec = float(scores["context_precision"])

    await log_ragas_run("evaluation", {"faithfulness": faith, "context_precision": prec})

    assert faith >= FAITHFULNESS_THRESHOLD, (
        f"evaluation faithfulness {faith:.3f} < {FAITHFULNESS_THRESHOLD}"
    )
    assert prec >= CONTEXT_PRECISION_THRESHOLD, (
        f"evaluation context precision {prec:.3f} < {CONTEXT_PRECISION_THRESHOLD}"
    )
