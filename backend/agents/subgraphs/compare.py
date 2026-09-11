from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agents.nodes import (
    after_grade_decision,
    bump_retry_node,
    compare_tool_node,
    fanout_retrieves,
    generate_node,
    grade_node,
    retrieve_one_node,
    rewrite_node,
    verify_node,
)
from backend.agents.state import AgentState


def build_compare_subgraph():
    """Compare path: rules engine first (mandatory), then policy retrieve for wording.

    Ranking/eligibility never come from the LLM — only from run_comparison tool.
    """
    graph = StateGraph(AgentState)
    graph.add_node("compare", compare_tool_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("retrieve_one", retrieve_one_node)
    graph.add_node("grade", grade_node)
    graph.add_node("retry", bump_retry_node)
    graph.add_node("generate", generate_node)
    graph.add_node("verify", verify_node)

    graph.add_edge(START, "compare")
    graph.add_edge("compare", "rewrite")
    graph.add_conditional_edges("rewrite", fanout_retrieves, ["retrieve_one"])
    graph.add_edge("retrieve_one", "grade")
    graph.add_conditional_edges(
        "grade",
        after_grade_decision,
        {"retry": "retry", "generate": "generate"},
    )
    graph.add_edge("retry", "rewrite")
    graph.add_edge("generate", "verify")
    graph.add_edge("verify", END)
    return graph.compile()
