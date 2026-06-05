from __future__ import annotations

import json
from typing import Any, TypedDict

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.guardrails import PIIRedactor, registry
from app.prompts import JOB_SETUP_CRITERIA_EXTRACTION, JOB_SETUP_SYSTEM

logger = structlog.get_logger()


class JobSetupState(TypedDict):
    conversation_history: list[dict[str, str]]
    criteria_draft: dict[str, Any] | None
    status: str  # "in_progress" | "confirming" | "completed"
    ai_message: str


def _build_llm() -> ChatOpenAI:
    from app.config import get_settings
    settings = get_settings()
    return ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0.3)


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
    ai_text = response.content

    if not registry.check_output(ai_text).passed:
        ai_text = "I apologize, let me rephrase. What skills are required for this role?"

    ai_text = PIIRedactor.redact(ai_text)

    status = "in_progress"
    if any(phrase in ai_text.lower() for phrase in ["to summarize", "here's a summary", "criteria confirmed"]):
        status = "confirming"

    return {**state, "ai_message": ai_text, "status": status}


async def confirm_criteria(state: JobSetupState) -> JobSetupState:
    conversation_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in state["conversation_history"]
    )

    response = await _build_llm().ainvoke(
        [
            SystemMessage(content=JOB_SETUP_CRITERIA_EXTRACTION),
            HumanMessage(content=conversation_text),
        ]
    )

    try:
        criteria = json.loads(response.content)
    except json.JSONDecodeError:
        return {
            **state,
            "ai_message": "Let me clarify a few more details. What are the required skills?",
            "status": "in_progress",
        }

    return {
        **state,
        "criteria_draft": criteria,
        "status": "completed",
        "ai_message": "I've captured the criteria. Please review them above and click Confirm to activate the job.",
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
