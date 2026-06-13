from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.nodes.interview_nodes import (
    InterviewState,
    check_input_guard,
    check_output_guard,
    generate_response,
)

# Re-exported so existing importers (`from app.graphs.interview_graph import
# InterviewState, interview_graph`) keep working after the node extraction.
__all__ = ["InterviewState", "build_interview_graph", "interview_graph"]


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
