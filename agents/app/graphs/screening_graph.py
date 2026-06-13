from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.nodes.screening_nodes import ScreeningState, score_cv

# Re-exported for existing importers after the node extraction.
__all__ = ["ScreeningState", "build_screening_graph", "screening_graph"]


def build_screening_graph() -> StateGraph:
    graph = StateGraph(ScreeningState)
    graph.add_node("score_cv", score_cv)
    graph.set_entry_point("score_cv")
    graph.add_edge("score_cv", END)
    return graph.compile()


screening_graph = build_screening_graph()
