from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.nodes.job_setup_nodes import (
    JobSetupState,
    confirm_criteria,
    elicit_criteria,
)

# Re-exported for existing importers after the node extraction.
__all__ = ["JobSetupState", "build_job_setup_graph", "job_setup_graph"]


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
