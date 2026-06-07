from __future__ import annotations

import json
from typing import Any, TypedDict

import structlog
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.guardrails import PIIRedactor, registry
from app.prompts.evaluation import (
    EVALUATION_SCORE_DIMENSIONS,
    EVALUATION_FLAG_CONSISTENCY,
    EVALUATION_SCORE_COMMUNICATION,
    EVALUATION_ASSESS_CONFIDENCE,
    EVALUATION_GENERATE_SUMMARY,
)

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


def _llm() -> ChatOpenAI:
    from app.config import get_settings
    settings = get_settings()
    return ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0.1)


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
        logger.warning("evaluation.guardrail_triggered.input", application_id=state["application_id"])
        return {**state, "guardrail_triggered": True}

    prompt = EVALUATION_SCORE_DIMENSIONS.format(
        criteria=json.dumps(state["job_criteria"], indent=2),
        transcript=transcript_str[:6000],
        cv_text=state["cv_text"][:3000],
    )
    response = await _llm().ainvoke([SystemMessage(content=prompt)])
    raw = response.content

    if not registry.check_output(raw).passed:
        logger.warning("evaluation.guardrail_triggered.output", application_id=state["application_id"])
        return {**state, "guardrail_triggered": True}

    try:
        data = json.loads(raw)
        scores = data.get("dimension_scores", [])
        redacted = []
        for dim in scores:
            redacted.append({
                "dimension": dim.get("dimension", ""),
                "score": int(dim.get("score", 0)),
                "evidence_quotes": [PIIRedactor.redact(q) for q in dim.get("evidence_quotes", [])],
            })
    except (json.JSONDecodeError, KeyError, ValueError):
        redacted = []

    return {**state, "dimension_scores": redacted}


async def flag_consistency(state: EvaluationState) -> EvaluationState:
    if state.get("guardrail_triggered"):
        return state

    transcript_str = _transcript_text(state["transcript"])
    prompt = EVALUATION_FLAG_CONSISTENCY.format(
        cv_text=state["cv_text"][:3000],
        transcript=transcript_str[:6000],
    )
    response = await _llm().ainvoke([SystemMessage(content=prompt)])
    raw = response.content

    if not registry.check_output(raw).passed:
        return {**state, "consistency_flags": []}

    try:
        data = json.loads(raw)
        flags = data.get("consistency_flags", [])
        redacted = [
            {
                "claim": PIIRedactor.redact(f.get("claim", "")),
                "cv_statement": PIIRedactor.redact(f.get("cv_statement", "")),
                "interview_statement": PIIRedactor.redact(f.get("interview_statement", "")),
                "flag_type": f.get("flag_type", "unverified"),
            }
            for f in flags
        ]
    except (json.JSONDecodeError, KeyError):
        redacted = []

    return {**state, "consistency_flags": redacted}


async def score_communication(state: EvaluationState) -> EvaluationState:
    if state.get("guardrail_triggered"):
        return state

    transcript_str = _transcript_text(state["transcript"])
    prompt = EVALUATION_SCORE_COMMUNICATION.format(transcript=transcript_str[:6000])
    response = await _llm().ainvoke([SystemMessage(content=prompt)])
    raw = response.content

    if not registry.check_output(raw).passed:
        default = {"response_depth": 0.5, "filler_word_frequency": 0.0, "deflection_frequency": 0.0}
        return {**state, "communication_quality": default}

    try:
        data = json.loads(raw)
        quality = data.get("communication_quality", {})
        quality = {
            "response_depth": float(quality.get("response_depth", 0.5)),
            "filler_word_frequency": float(quality.get("filler_word_frequency", 0.0)),
            "deflection_frequency": float(quality.get("deflection_frequency", 0.0)),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        quality = {"response_depth": 0.5, "filler_word_frequency": 0.0, "deflection_frequency": 0.0}

    return {**state, "communication_quality": quality}


async def assess_confidence(state: EvaluationState) -> EvaluationState:
    if state.get("guardrail_triggered"):
        return state

    avg_evidence = (
        sum(len(d.get("evidence_quotes", [])) for d in state["dimension_scores"]) / max(len(state["dimension_scores"]), 1)
    )
    turn_depth = state["communication_quality"].get("response_depth", 0.5)

    # Fast-path: apply rule directly without LLM when evidence is clearly sufficient
    if avg_evidence >= 1 and turn_depth >= 0.3:
        return {**state, "confidence_flag": False, "confidence_reason": None}

    prompt = EVALUATION_ASSESS_CONFIDENCE.format(
        dimension_scores=json.dumps(state["dimension_scores"]),
        communication_quality=json.dumps(state["communication_quality"]),
    )
    response = await _llm().ainvoke([SystemMessage(content=prompt)])
    raw = response.content

    try:
        data = json.loads(raw)
        flag = bool(data.get("confidence_flag", False))
        reason = data.get("confidence_reason") or None
        if reason:
            reason = PIIRedactor.redact(reason)
    except (json.JSONDecodeError, KeyError):
        flag = avg_evidence < 1 or turn_depth < 0.3
        reason = "Insufficient evidence to assess candidate confidently." if flag else None

    return {**state, "confidence_flag": flag, "confidence_reason": reason}


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
    raw = PIIRedactor.redact(response.content)

    return {**state, "overall_score": overall, "recommendation": recommendation, "summary": raw}


def _build_graph() -> StateGraph:
    builder = StateGraph(EvaluationState)
    builder.add_node("score_dimensions", score_dimensions)
    builder.add_node("flag_consistency", flag_consistency)
    builder.add_node("score_communication", score_communication)
    builder.add_node("assess_confidence", assess_confidence)
    builder.add_node("generate_summary", generate_summary)

    builder.set_entry_point("score_dimensions")
    builder.add_edge("score_dimensions", "flag_consistency")
    builder.add_edge("flag_consistency", "score_communication")
    builder.add_edge("score_communication", "assess_confidence")
    builder.add_edge("assess_confidence", "generate_summary")
    builder.add_edge("generate_summary", END)

    return builder.compile()


evaluation_graph = _build_graph()
