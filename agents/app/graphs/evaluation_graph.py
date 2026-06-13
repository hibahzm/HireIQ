from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.nodes.evaluation_nodes import (
    EvaluationState,
    assess_confidence,
    flag_consistency,
    generate_summary,
    score_communication,
    score_dimensions,
)

# Re-exported for existing importers after the node extraction.
__all__ = ["EvaluationState", "build_evaluation_graph", "evaluation_graph"]


def build_evaluation_graph() -> StateGraph:
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


evaluation_graph = build_evaluation_graph()
