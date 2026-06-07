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

import httpx
import pytest

from tests.ragas.conftest import (
    AGENTS_BASE_URL,
    CONTEXT_PRECISION_THRESHOLD,
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
                    "job_criteria": criteria,
                    "hybrid_search_results": [{"chunk_text": c} for c in chunks],
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

    scores = evaluate(ds, metrics=[faithfulness, context_precision])
    faith = float(scores["faithfulness"])
    prec = float(scores["context_precision"])

    await log_ragas_run("screening", {"faithfulness": faith, "context_precision": prec})

    assert faith >= FAITHFULNESS_THRESHOLD, (
        f"screening faithfulness {faith:.3f} < {FAITHFULNESS_THRESHOLD}"
    )
    assert prec >= CONTEXT_PRECISION_THRESHOLD, (
        f"screening context precision {prec:.3f} < {CONTEXT_PRECISION_THRESHOLD}"
    )
