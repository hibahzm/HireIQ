"""Nodes for the evaluation agent graph.

Graph wiring lives in ``app.graphs.evaluation_graph``.
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

import structlog
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from app.graphs.json_utils import parse_json_object
from app.guardrails import PIIRedactor, registry
from app.prompts.evaluation import (
    EVALUATION_ASSESS_CONFIDENCE,
    EVALUATION_FLAG_CONSISTENCY,
    EVALUATION_GENERATE_SUMMARY,
    EVALUATION_SCORE_COMMUNICATION,
    EVALUATION_SCORE_DIMENSIONS,
)
from app.usage import append_usage_event

logger = structlog.get_logger()


class EvaluationState(TypedDict):
    application_id: str
    company_id: str
    cv_text: str
    job_criteria: dict[str, Any]
    transcript: list[dict[str, Any]]
    # accumulated
    dimension_scores: list[dict[str, Any]]
    consistency_flags: list[dict[str, Any]]
    communication_quality: dict[str, Any]
    overall_score: int
    recommendation: str
    confidence_flag: bool
    confidence_reason: str | None
    summary: str | None
    guardrail_triggered: bool
    usage_events: list[dict[str, Any]]


def _llm(json_mode: bool = False) -> ChatOpenAI:
    from app.config import get_settings

    settings = get_settings()
    kwargs: dict[str, Any] = {}
    if json_mode:
        # Forces syntactically valid JSON output — parse failures here previously
        # produced empty dimension_scores and spurious low-confidence flags.
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatOpenAI(
        model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0.1, **kwargs
    )


def _transcript_text(transcript: list[dict[str, Any]]) -> str:
    lines = []
    for turn in transcript:
        speaker = turn.get("speaker", "unknown").upper()
        text = turn.get("content_text", "")
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


async def score_dimensions(state: EvaluationState) -> EvaluationState:
    transcript_str = _transcript_text(state["transcript"])

    if not registry.check_input(transcript_str).passed:
        logger.warning(
            "evaluation.guardrail_triggered.input", application_id=state["application_id"]
        )
        return {**state, "guardrail_triggered": True}

    prompt = EVALUATION_SCORE_DIMENSIONS.format(
        criteria=json.dumps(state["job_criteria"], indent=2),
        transcript=transcript_str[:6000],
        cv_text=state["cv_text"][:3000],
    )
    response = await _llm(json_mode=True).ainvoke([SystemMessage(content=prompt)])
    usage_events = append_usage_event(
        state,
        response,
        agent_type="evaluation",
        metadata={"application_id": state["application_id"], "operation": "score_dimensions"},
    )
    raw = response.content

    if not registry.check_output(raw).passed:
        logger.warning(
            "evaluation.guardrail_triggered.output", application_id=state["application_id"]
        )
        return {**state, "guardrail_triggered": True, "usage_events": usage_events}

    data = parse_json_object(raw) or {}
    redacted = []
    for dim in data.get("dimension_scores", []):
        try:
            redacted.append(
                {
                    "dimension": str(dim.get("dimension", "")),
                    "score": int(dim.get("score", 0)),
                    "evidence_quotes": [
                        PIIRedactor.redact(str(q)) for q in dim.get("evidence_quotes", [])
                    ],
                }
            )
        except (TypeError, ValueError):
            continue
    if not redacted:
        logger.warning(
            "evaluation.score_dimensions_unparseable", application_id=state["application_id"]
        )

    return {**state, "dimension_scores": redacted, "usage_events": usage_events}


async def flag_consistency(state: EvaluationState) -> EvaluationState:
    if state.get("guardrail_triggered"):
        return state

    transcript_str = _transcript_text(state["transcript"])
    prompt = EVALUATION_FLAG_CONSISTENCY.format(
        cv_text=state["cv_text"][:3000],
        transcript=transcript_str[:6000],
    )
    response = await _llm(json_mode=True).ainvoke([SystemMessage(content=prompt)])
    usage_events = append_usage_event(
        state,
        response,
        agent_type="evaluation",
        metadata={"application_id": state["application_id"], "operation": "flag_consistency"},
    )
    raw = response.content

    if not registry.check_output(raw).passed:
        return {**state, "consistency_flags": [], "usage_events": usage_events}

    data = parse_json_object(raw) or {}
    redacted = [
        {
            "claim": PIIRedactor.redact(str(f.get("claim", ""))),
            "cv_statement": PIIRedactor.redact(str(f.get("cv_statement", ""))),
            "interview_statement": PIIRedactor.redact(str(f.get("interview_statement", ""))),
            "flag_type": f.get("flag_type", "unverified"),
        }
        for f in data.get("consistency_flags", [])
        if isinstance(f, dict)
    ]

    return {**state, "consistency_flags": redacted, "usage_events": usage_events}


async def score_communication(state: EvaluationState) -> EvaluationState:
    if state.get("guardrail_triggered"):
        return state

    transcript_str = _transcript_text(state["transcript"])
    prompt = EVALUATION_SCORE_COMMUNICATION.format(transcript=transcript_str[:6000])
    response = await _llm(json_mode=True).ainvoke([SystemMessage(content=prompt)])
    usage_events = append_usage_event(
        state,
        response,
        agent_type="evaluation",
        metadata={"application_id": state["application_id"], "operation": "score_communication"},
    )
    raw = response.content

    if not registry.check_output(raw).passed:
        default = {"response_depth": 0.5, "filler_word_frequency": 0.0, "deflection_frequency": 0.0}
        return {**state, "communication_quality": default, "usage_events": usage_events}

    data = parse_json_object(raw) or {}
    try:
        parsed_quality = data.get("communication_quality", {})
        quality = {
            "response_depth": float(parsed_quality.get("response_depth", 0.5)),
            "filler_word_frequency": float(parsed_quality.get("filler_word_frequency", 0.0)),
            "deflection_frequency": float(parsed_quality.get("deflection_frequency", 0.0)),
        }
    except (AttributeError, TypeError, ValueError):
        quality = {"response_depth": 0.5, "filler_word_frequency": 0.0, "deflection_frequency": 0.0}

    return {**state, "communication_quality": quality, "usage_events": usage_events}


async def assess_confidence(state: EvaluationState) -> EvaluationState:
    if state.get("guardrail_triggered"):
        return state

    avg_evidence = sum(len(d.get("evidence_quotes", [])) for d in state["dimension_scores"]) / max(
        len(state["dimension_scores"]), 1
    )
    turn_depth = state["communication_quality"].get("response_depth", 0.5)

    # Fast-path: apply rule directly without LLM when evidence is clearly sufficient
    if avg_evidence >= 1 and turn_depth >= 0.3:
        return {**state, "confidence_flag": False, "confidence_reason": None}

    prompt = EVALUATION_ASSESS_CONFIDENCE.format(
        dimension_scores=json.dumps(state["dimension_scores"]),
        communication_quality=json.dumps(state["communication_quality"]),
    )
    response = await _llm(json_mode=True).ainvoke([SystemMessage(content=prompt)])
    usage_events = append_usage_event(
        state,
        response,
        agent_type="evaluation",
        metadata={"application_id": state["application_id"], "operation": "assess_confidence"},
    )
    raw = response.content

    data = parse_json_object(raw)
    if data is not None:
        flag = bool(data.get("confidence_flag", False))
        reason = data.get("confidence_reason") or None
        if reason:
            reason = PIIRedactor.redact(str(reason))
    else:
        flag = avg_evidence < 1 or turn_depth < 0.3
        reason = "Insufficient evidence to assess candidate confidently." if flag else None

    return {
        **state,
        "confidence_flag": flag,
        "confidence_reason": reason,
        "usage_events": usage_events,
    }


async def generate_summary(state: EvaluationState) -> EvaluationState:
    if state.get("guardrail_triggered"):
        # Compute overall_score + recommendation from dimension_scores even on guardrail path
        scores = [d.get("score", 0) for d in state["dimension_scores"]]
        overall = int(sum(scores) / max(len(scores), 1)) if scores else 0
        rec = "hire" if overall >= 75 else ("uncertain" if overall >= 50 else "no_hire")
        return {**state, "overall_score": overall, "recommendation": rec, "summary": None}

    # Compute weighted overall score
    dimensions = state["job_criteria"].get("evaluation_dimensions", [])
    weight_map = {d["name"]: d.get("weight", 0) for d in dimensions}
    total_weight = sum(weight_map.values()) or 1.0

    weighted_sum = 0.0
    for dim in state["dimension_scores"]:
        w = weight_map.get(dim["dimension"], 1.0 / max(len(state["dimension_scores"]), 1))
        weighted_sum += dim["score"] * w
    overall = int(weighted_sum / total_weight)
    recommendation = "hire" if overall >= 75 else ("uncertain" if overall >= 50 else "no_hire")

    prompt = EVALUATION_GENERATE_SUMMARY.format(
        overall_score=overall,
        recommendation=recommendation,
        dimension_scores=json.dumps(state["dimension_scores"]),
        consistency_flags=json.dumps(state["consistency_flags"]),
        communication_quality=json.dumps(state["communication_quality"]),
    )
    response = await _llm().ainvoke([SystemMessage(content=prompt)])
    usage_events = append_usage_event(
        state,
        response,
        agent_type="evaluation",
        metadata={"application_id": state["application_id"], "operation": "generate_summary"},
    )
    raw = PIIRedactor.redact(response.content)

    return {
        **state,
        "overall_score": overall,
        "recommendation": recommendation,
        "summary": raw,
        "usage_events": usage_events,
    }
