from __future__ import annotations

from typing import Any, TypedDict

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.guardrails import PIIRedactor, registry

logger = structlog.get_logger()

_SYSTEM_PROMPT = """You are a professional AI interviewer conducting a structured job interview.

Job criteria and evaluation dimensions:
{criteria}

Dimensions to cover: {dimensions}

Your goals:
- Ask one clear, focused question per turn
- Explore each evaluation dimension through 2-3 questions
- Adapt follow-up questions based on candidate responses
- Do NOT ask for personal information (address, date of birth, etc.)
- Keep responses professional and concise (1-2 sentences max)

When all dimensions are adequately covered OR max_turns is reached, end the interview by saying
exactly: "Thank you for completing this interview. [INTERVIEW_COMPLETE]"
"""


class InterviewState(TypedDict):
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


def _build_llm() -> ChatOpenAI:
    from app.config import get_settings
    settings = get_settings()
    return ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0.4)


async def check_input_guard(state: InterviewState) -> InterviewState:
    last_user_msg = next(
        (m["content"] for m in reversed(state["conversation_history"]) if m["role"] == "user"),
        "",
    )
    result = registry.check_input(last_user_msg)
    if not result.passed:
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

    criteria_text = str(state["job_criteria"])
    dimensions_text = ", ".join(state["dimensions_remaining"]) or "general competencies"

    system = _SYSTEM_PROMPT.format(criteria=criteria_text, dimensions=dimensions_text)
    messages = [SystemMessage(content=system)]

    for msg in state["conversation_history"]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    llm = _build_llm()
    response = await llm.ainvoke(messages)
    ai_text = response.content

    session_complete = "[INTERVIEW_COMPLETE]" in ai_text
    ai_text = ai_text.replace("[INTERVIEW_COMPLETE]", "").strip()

    # Check if max_turns reached
    if state["turn_count"] + 1 >= state["max_turns"]:
        session_complete = True
        if not ai_text.lower().startswith("thank you"):
            ai_text = "Thank you for completing this interview. Your responses have been recorded."

    return {
        **state,
        "ai_response": ai_text,
        "session_complete": session_complete,
        "guardrail_triggered": False,
    }


async def check_output_guard(state: InterviewState) -> InterviewState:
    if state.get("blocked_redirect"):
        return {**state, "ai_response": state["blocked_redirect"]}

    ai_text = state.get("ai_response", "")
    result = registry.check_output(ai_text)
    if not result.passed:
        return {
            **state,
            "ai_response": "Let's continue. Could you tell me about your approach to teamwork?",
            "guardrail_triggered": True,
        }

    redacted = PIIRedactor.redact(ai_text)
    return {**state, "ai_response": redacted}


def build_interview_graph():
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
