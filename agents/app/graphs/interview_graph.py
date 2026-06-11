from __future__ import annotations

from typing import Any, TypedDict

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.guardrails import PIIRedactor, registry
from app.prompts import INTERVIEW_SYSTEM
from app.usage import append_usage_event

logger = structlog.get_logger()


class InterviewState(TypedDict):
    company_id: str
    session_id: str | None
    conversation_history: list[dict[str, str]]
    dimensions_covered: list[str]
    dimensions_remaining: list[str]
    turn_count: int
    max_turns: int
    job_criteria: dict[str, Any]
    ai_response: str
    session_complete: bool
    guardrail_triggered: bool
    blocked_redirect: str | None
    usage_events: list[dict[str, Any]]


def _build_llm() -> ChatOpenAI:
    from app.config import get_settings
    settings = get_settings()
    return ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0.4)


async def check_input_guard(state: InterviewState) -> InterviewState:
    last_user_msg = next(
        (m["content"] for m in reversed(state["conversation_history"]) if m["role"] == "user"),
        "",
    )
    if not registry.check_input(last_user_msg).passed:
        return {
            **state,
            "guardrail_triggered": True,
            "blocked_redirect": (
                "I'm sorry, I can't continue this line of conversation. "
                "Let's focus on the role. Could you tell me more about your relevant experience?"
            ),
        }
    return {**state, "guardrail_triggered": False, "blocked_redirect": None}


async def generate_response(state: InterviewState) -> InterviewState:
    if state["guardrail_triggered"]:
        return state

    dimensions_text = ", ".join(state["dimensions_remaining"]) or "general competencies"
    system = INTERVIEW_SYSTEM.format(
        criteria=str(state["job_criteria"]),
        dimensions=dimensions_text,
    )

    messages = [SystemMessage(content=system)]
    for msg in state["conversation_history"]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    response = await _build_llm().ainvoke(messages)
    usage_events = append_usage_event(
        state,
        response,
        agent_type="interview",
        metadata={"session_id": state.get("session_id")},
    )
    ai_text = response.content

    session_complete = "[INTERVIEW_COMPLETE]" in ai_text
    ai_text = ai_text.replace("[INTERVIEW_COMPLETE]", "").strip()

    if state["turn_count"] + 1 >= state["max_turns"]:
        session_complete = True
        if not ai_text.lower().startswith("thank you"):
            ai_text = "Thank you for completing this interview. Your responses have been recorded."

    return {
        **state,
        "ai_response": ai_text,
        "session_complete": session_complete,
        "guardrail_triggered": False,
        "usage_events": usage_events,
    }


async def check_output_guard(state: InterviewState) -> InterviewState:
    if state.get("blocked_redirect"):
        return {**state, "ai_response": state["blocked_redirect"]}

    ai_text = state.get("ai_response", "")
    if not registry.check_output(ai_text).passed:
        return {
            **state,
            "ai_response": "Let's continue. Could you tell me about your approach to teamwork?",
            "guardrail_triggered": True,
        }

    return {**state, "ai_response": PIIRedactor.redact(ai_text)}


def build_interview_graph() -> StateGraph:
    graph = StateGraph(InterviewState)
    graph.add_node("check_input_guard", check_input_guard)
    graph.add_node("generate_response", generate_response)
    graph.add_node("check_output_guard", check_output_guard)
    graph.set_entry_point("check_input_guard")
    graph.add_edge("check_input_guard", "generate_response")
    graph.add_edge("generate_response", "check_output_guard")
    graph.add_edge("check_output_guard", END)
    return graph.compile()


interview_graph = build_interview_graph()
