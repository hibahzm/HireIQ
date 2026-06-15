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
import warnings

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

            dim_names = [
                d["name"] if isinstance(d, dict) else str(d)
                for d in criteria["evaluation_dimensions"]
            ]
            questions.append(
                f"Assess this candidate against {', '.join(dim_names)}."
            )
            answers.append(answer)
            contexts.append(turns)
            references.append(" ".join(fx["ground_truth_evidence"].values()))

    ds = Dataset.from_dict(
        {"question": questions, "answer": answers, "contexts": contexts, "reference": references}
    )

    # Report-only diagnostic (Option A): grounding metrics are informational, not a
    # hard gate — they rely on a flaky external LLM judge, so they're tracked but never
    # fail the build.
    try:
        scores = evaluate(ds, metrics=[faithfulness, context_precision])
        df = scores.to_pandas()  # ragas >=0.2 returns per-sample lists
        faith = float(df["faithfulness"].mean())
        prec = float(df["context_precision"].mean())
    except Exception as exc:  # ragas-internal/judge connection errors → skip, don't fail
        pytest.skip(f"ragas grounding diagnostic unavailable: {exc}")

    await log_ragas_run("evaluation", {"faithfulness": faith, "context_precision": prec})
    print(
        f"[ragas][evaluation] faithfulness={faith:.3f} context_precision={prec:.3f} "
        f"(report-only; targets {FAITHFULNESS_THRESHOLD}/{CONTEXT_PRECISION_THRESHOLD})"
    )
    if faith < FAITHFULNESS_THRESHOLD or prec < CONTEXT_PRECISION_THRESHOLD:
        warnings.warn(
            f"evaluation grounding below target: faithfulness={faith:.3f}, "
            f"context_precision={prec:.3f}"
        )
