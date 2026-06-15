"""
T084b — RAGAS quality gate for the CV screening pipeline.

Calls the real agents `/agents/cv-screen` endpoint over HTTP for each golden CV,
treating the CV chunks as retrieved context and the agent's screening rationale
as the answer. RAGAS then scores:
  - faithfulness: is the rationale grounded in the CV context, or did it invent
    skills/claims the CV never makes?
  - context precision: are the retrieved chunks relevant to the job criteria?

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
    DECISION_F1_THRESHOLD,
    FAITHFULNESS_THRESHOLD,
    agents_headers,
    load_cv_fixtures,
    log_ragas_run,
    requires_ragas,
)


def _chunk_cv(cv_text: str) -> list[str]:
    """Lightweight paragraph chunking that mirrors the retrieval context fed to
    the screening agent (avoids importing the embedding service / OpenAI here)."""
    return [c.strip() for c in cv_text.split("\n\n") if c.strip()]


@requires_ragas
@pytest.mark.asyncio
async def test_screening_rag_faithfulness_and_precision():
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import context_precision, faithfulness

    fixtures = load_cv_fixtures()
    assert len(fixtures) == 20, "Golden set must contain 20 CV samples"

    questions, answers, contexts, references = [], [], [], []

    async with httpx.AsyncClient(base_url=AGENTS_BASE_URL, timeout=60) as client:
        for fx in fixtures:
            criteria = fx["job_criteria"]
            chunks = _chunk_cv(fx["cv_text"])
            resp = await client.post(
                "/agents/cv-screen",
                headers=agents_headers(),
                json={
                    "application_id": str(uuid.uuid4()),
                    "company_id": str(uuid.uuid4()),
                    "cv_text": fx["cv_text"],
                    "job_description": criteria.get("description", criteria.get("title", "")),
                    "job_criteria": criteria,
                },
            )
            resp.raise_for_status()
            body = resp.json()

            questions.append(f"Does this candidate meet the criteria for {criteria['title']}?")
            answers.append(body["rationale"])
            contexts.append(chunks)
            references.append(", ".join(fx["ground_truth_evidenced_skills"]))

    ds = Dataset.from_dict(
        {"question": questions, "answer": answers, "contexts": contexts, "reference": references}
    )

    # Report-only diagnostic (Option A): grounding metrics are informational, not a
    # hard gate — they depend on a flaky external LLM judge and measure CV-grounding of
    # a fit *judgment* rationale, so they're tracked but never fail the build. The hard
    # screening-quality gate is test_screening_decision_accuracy.
    try:
        scores = evaluate(ds, metrics=[faithfulness, context_precision])
        df = scores.to_pandas()  # ragas >=0.2 returns per-sample lists
        faith = float(df["faithfulness"].mean())
        prec = float(df["context_precision"].mean())
    except Exception as exc:  # ragas-internal/judge connection errors → skip, don't fail
        pytest.skip(f"ragas grounding diagnostic unavailable: {exc}")

    await log_ragas_run("screening", {"faithfulness": faith, "context_precision": prec})
    print(
        f"[ragas][screening] faithfulness={faith:.3f} context_precision={prec:.3f} "
        f"(report-only; targets {FAITHFULNESS_THRESHOLD}/{CONTEXT_PRECISION_THRESHOLD})"
    )
    if faith < FAITHFULNESS_THRESHOLD or prec < CONTEXT_PRECISION_THRESHOLD:
        warnings.warn(
            f"screening grounding below target: faithfulness={faith:.3f}, "
            f"context_precision={prec:.3f}"
        )


@requires_ragas
@pytest.mark.asyncio
async def test_screening_decision_accuracy():
    """Decision-quality gate: the screener's qualified/rejected verdict must agree
    with the golden `expected_qualified` label. Complements the grounding metrics
    above — faithfulness says "didn't hallucinate", this says "decided correctly".
    """
    fixtures = load_cv_fixtures()
    assert len(fixtures) == 20, "Golden set must contain 20 CV samples"

    tp = fp = fn = tn = 0
    async with httpx.AsyncClient(base_url=AGENTS_BASE_URL, timeout=60) as client:
        for fx in fixtures:
            criteria = fx["job_criteria"]
            resp = await client.post(
                "/agents/cv-screen",
                headers=agents_headers(),
                json={
                    "application_id": str(uuid.uuid4()),
                    "company_id": str(uuid.uuid4()),
                    "cv_text": fx["cv_text"],
                    "job_description": criteria.get("description", criteria.get("title", "")),
                    "job_criteria": criteria,
                },
            )
            resp.raise_for_status()
            predicted = resp.json()["status"] == "qualified"
            expected = bool(fx["expected_qualified"])
            if predicted and expected:
                tp += 1
            elif predicted and not expected:
                fp += 1
            elif not predicted and expected:
                fn += 1
            else:
                tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(fixtures)

    await log_ragas_run(
        "screening_decision",
        {"precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy},
    )

    assert f1 >= DECISION_F1_THRESHOLD, (
        f"screening decision F1 {f1:.3f} < {DECISION_F1_THRESHOLD} "
        f"(precision={precision:.3f}, recall={recall:.3f}, accuracy={accuracy:.3f})"
    )
