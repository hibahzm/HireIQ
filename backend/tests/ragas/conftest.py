"""
Shared fixtures and helpers for the RAGAS quality suite (T084b).

These tests score the *grounding quality* of the LLM pipelines against a curated
golden set:
  - faithfulness  ≥ 0.85  (rationale/evidence is grounded in retrieved context;
                            no hallucinated skills or quotes)
  - context precision ≥ 0.80 (retrieved/used context is relevant to the criteria)

They require a real OpenAI key (RAGAS uses an LLM judge) and are skipped in the
normal unit/integration CI lane. A dedicated CI job runs them with a real key
and fails the build if a threshold is breached.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

FAITHFULNESS_THRESHOLD = 0.85
CONTEXT_PRECISION_THRESHOLD = 0.80


def _has_real_openai_key() -> bool:
    key = os.environ.get("OPENAI_API_KEY", "")
    return bool(key) and not key.startswith("sk-fake")


def _agents_reachable() -> bool:
    return bool(os.environ.get("AGENTS_BASE_URL"))


# Requires (a) a real OpenAI key for the RAGAS LLM judge AND (b) a running
# agents service to exercise the real pipeline contract over HTTP.
requires_ragas = pytest.mark.skipif(
    not (_has_real_openai_key() and _agents_reachable()),
    reason="RAGAS suite needs a real OPENAI_API_KEY and a running agents service "
    "(AGENTS_BASE_URL). Run in the dedicated RAGAS CI job.",
)

AGENTS_BASE_URL = os.environ.get("AGENTS_BASE_URL", "http://localhost:8001")
AGENTS_INTERNAL_SECRET = os.environ.get("AGENTS_INTERNAL_SECRET", "")


def agents_headers() -> dict[str, str]:
    return {"X-Internal-Secret": AGENTS_INTERNAL_SECRET}


def load_cv_fixtures() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((FIXTURES / "cvs").glob("*.json"))]


def load_transcript_fixtures() -> list[dict]:
    return [
        json.loads(p.read_text())
        for p in sorted((FIXTURES / "transcripts").glob("*.json"))
    ]


async def log_ragas_run(pipeline: str, scores: dict[str, float]) -> None:
    """Best-effort: persist per-run RAGAS scores to audit_log under
    `pipeline.quality.ragas`. Never fails the test if the DB is unreachable —
    the threshold assertions are the hard gate."""
    try:
        from app.db import _get_session_factory
        from app.repositories.audit_log_repository import AuditLogRepository

        async with _get_session_factory()() as session:
            async with session.begin():
                await AuditLogRepository(session).log_event(
                    event_type="pipeline.quality.ragas",
                    actor_type="system",
                    entity_type="pipeline",
                    entity_id=pipeline,
                    metadata={"pipeline": pipeline, "scores": scores},
                )
    except Exception:  # noqa: BLE001 — observability is best-effort here
        pass
