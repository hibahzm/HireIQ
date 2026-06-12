from __future__ import annotations

import json
from typing import Any, TypedDict

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.guardrails import PIIRedactor, registry
from app.prompts import JOB_SETUP_CRITERIA_EXTRACTION, JOB_SETUP_SYSTEM
from app.usage import append_usage_event

logger = structlog.get_logger()


class JobSetupState(TypedDict):
    job_id: str
    company_id: str
    conversation_history: list[dict[str, str]]
    criteria_draft: dict[str, Any] | None
    status: str  # "in_progress" | "confirming" | "completed"
    ai_message: str
    usage_events: list[dict[str, Any]]


def _build_llm() -> ChatOpenAI:
    from app.config import get_settings
    settings = get_settings()
    return ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0.3)


def _completion_signal(text: str) -> bool:
    normalized = (
        text.lower()
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    if "status" in normalized and "completed" in normalized:
        return True
    return any(
        phrase in normalized
        for phrase in (
            "criteria confirmed",
            "confirm to activate",
            "ready to activate",
            "setup complete",
            "setup is complete",
            "here's the summary",
            "here is the summary",
            "structured summary",
        )
    )


def _parse_json_object(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    for candidate in (text, text[text.find("{") : text.rfind("}") + 1]):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        return parsed if isinstance(parsed, dict) else None
    return None


def _normalise_criteria(criteria: dict[str, Any]) -> dict[str, Any]:
    return {
        "required_skills": criteria.get("required_skills") or [],
        "optional_skills": criteria.get("optional_skills") or [],
        "experience_level": criteria.get("experience_level") or "mid",
        "min_years_experience": criteria.get("min_years_experience"),
        "evaluation_dimensions": criteria.get("evaluation_dimensions") or [
            {"name": "Role fit", "weight": 1.0, "description": "Overall match for the role"}
        ],
        "dealbreakers": criteria.get("dealbreakers") or [],
        "min_screening_score": criteria.get("min_screening_score") or 60,
    }


async def elicit_criteria(state: JobSetupState) -> JobSetupState:
    user_message = state["conversation_history"][-1]["content"] if state["conversation_history"] else ""

    if not registry.check_input(user_message).passed:
        return {
            **state,
            "ai_message": "I'm sorry, I can't respond to that. Let's focus on the job criteria.",
            "status": "in_progress",
        }

    messages = [SystemMessage(content=JOB_SETUP_SYSTEM)]
    for msg in state["conversation_history"]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    response = await _build_llm().ainvoke(messages)
    usage_events = append_usage_event(
        state,
        response,
        agent_type="job_setup",
        metadata={"job_id": state["job_id"], "operation": "elicit_criteria"},
    )
    ai_text = response.content

    if not registry.check_output(ai_text).passed:
        ai_text = "I apologize, let me rephrase. What skills are required for this role?"

    ai_text = PIIRedactor.redact(ai_text)

    status = "confirming" if _completion_signal(ai_text) else "in_progress"

    return {**state, "ai_message": ai_text, "status": status, "usage_events": usage_events}


async def confirm_criteria(state: JobSetupState) -> JobSetupState:
    history = list(state["conversation_history"])
    if state.get("ai_message"):
        history.append({"role": "assistant", "content": state["ai_message"]})

    conversation_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in history
    )

    response = await _build_llm().ainvoke(
        [
            SystemMessage(content=JOB_SETUP_CRITERIA_EXTRACTION),
            HumanMessage(content=conversation_text),
        ]
    )
    usage_events = append_usage_event(
        state,
        response,
        agent_type="job_setup",
        metadata={"job_id": state["job_id"], "operation": "confirm_criteria"},
    )

    criteria = _parse_json_object(str(response.content))
    if criteria is None:
        return {
            **state,
            "ai_message": "Let me clarify a few more details. What are the required skills?",
            "status": "in_progress",
            "usage_events": usage_events,
        }

    criteria = _normalise_criteria(criteria)

    return {
        **state,
        "criteria_draft": criteria,
        "status": "completed",
        "ai_message": "I've captured the criteria. Please review them above and click Confirm to activate the job.",
        "usage_events": usage_events,
    }


def _route(state: JobSetupState) -> str:
    if state["status"] == "confirming":
        return "confirm"
    if state["status"] == "completed":
        return END
    return "elicit"


def build_job_setup_graph() -> StateGraph:
    graph = StateGraph(JobSetupState)
    graph.add_node("elicit", elicit_criteria)
    graph.add_node("confirm", confirm_criteria)
    graph.set_entry_point("elicit")
    graph.add_conditional_edges("elicit", _route, {"confirm": "confirm", "elicit": END, END: END})
    graph.add_edge("confirm", END)
    return graph.compile()


job_setup_graph = build_job_setup_graph()
