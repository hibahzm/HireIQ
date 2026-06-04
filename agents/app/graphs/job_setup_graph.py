from __future__ import annotations

from typing import Any, TypedDict

import structlog
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.guardrails import PIIRedactor, registry

logger = structlog.get_logger()

_SYSTEM_PROMPT = """You are a hiring assistant helping a recruiter define evaluation criteria for a job position.

Your goals:
1. Ask about required skills and experience level
2. Ask about evaluation dimensions (e.g., technical skills, communication, culture fit)
3. Ask about dealbreakers (automatic rejection conditions)
4. Ask about the minimum screening score threshold (0-100)
5. Confirm and summarize the criteria once all information is gathered

Respond concisely. Ask one focused question at a time.
When you have gathered all criteria, respond with status="completed" and provide a structured summary.
Never ask for or share personal information about candidates."""

_CRITERIA_EXTRACTION_PROMPT = """Based on the conversation so far, extract the job criteria as structured JSON.

Return ONLY valid JSON with this schema:
{
  "required_skills": [{"skill": "string", "priority": "required"}],
  "optional_skills": [{"skill": "string", "priority": "nice_to_have"}],
  "experience_level": "junior|mid|senior|lead",
  "min_years_experience": null or integer,
  "evaluation_dimensions": [{"name": "string", "weight": number, "description": "string"}],
  "dealbreakers": ["string"],
  "min_screening_score": integer (0-100)
}

Weights in evaluation_dimensions MUST sum to 1.0.
If information is missing, use reasonable defaults."""


class JobSetupState(TypedDict):
    conversation_history: list[dict[str, str]]
    criteria_draft: dict[str, Any] | None
    status: str  # "in_progress" | "completed"
    ai_message: str


def _build_llm() -> ChatOpenAI:
    from app.config import get_settings
    settings = get_settings()
    return ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.OPENAI_API_KEY,
        temperature=0.3,
    )


async def elicit_criteria(state: JobSetupState) -> JobSetupState:
    """Generate the next conversational turn to elicit job criteria."""
    user_message = state["conversation_history"][-1]["content"] if state["conversation_history"] else ""

    guard_result = registry.check_input(user_message)
    if not guard_result.passed:
        return {
            **state,
            "ai_message": "I'm sorry, I can't respond to that. Let's focus on the job criteria.",
            "status": "in_progress",
        }

    llm = _build_llm()
    messages = [SystemMessage(content=_SYSTEM_PROMPT)]
    for msg in state["conversation_history"]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            from langchain_core.messages import AIMessage
            messages.append(AIMessage(content=msg["content"]))

    response = await llm.ainvoke(messages)
    ai_text = response.content

    output_guard = registry.check_output(ai_text)
    if not output_guard.passed:
        ai_text = "I apologize, let me rephrase. What skills are required for this role?"

    ai_text = PIIRedactor.redact(ai_text)

    # Heuristic: if the AI says it has all the info, transition to confirm
    status = "in_progress"
    if any(phrase in ai_text.lower() for phrase in ["to summarize", "here's a summary", "criteria confirmed"]):
        status = "confirming"

    return {**state, "ai_message": ai_text, "status": status}


async def confirm_criteria(state: JobSetupState) -> JobSetupState:
    """Extract structured criteria from the conversation and confirm with the user."""
    llm = _build_llm()
    conversation_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in state["conversation_history"]
    )
    response = await llm.ainvoke(
        [
            SystemMessage(content=_CRITERIA_EXTRACTION_PROMPT),
            HumanMessage(content=conversation_text),
        ]
    )

    import json
    try:
        criteria = json.loads(response.content)
    except json.JSONDecodeError:
        # Fallback: keep confirming
        return {**state, "ai_message": "Let me clarify a few more details. What are the required skills?", "status": "in_progress"}

    return {
        **state,
        "criteria_draft": criteria,
        "status": "completed",
        "ai_message": (
            "I've captured the criteria. Please review them above and click Confirm to activate the job."
        ),
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
