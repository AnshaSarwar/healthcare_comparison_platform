from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agents.nodes import (
    after_grade_decision,
    bump_retry_node,
    fanout_retrieves,
    generate_node,
    grade_node,
    retrieve_one_node,
    rewrite_node,
    verify_node,
)
from backend.agents.state import AgentState


def build_policy_subgraph():
    """Policy Q&A: rewrite → parallel retrieve → grade → bounded retry → generate → verify.

    Structured CRAG pipeline is the right fit for grounded booklet answers — not open ReAct.
    """
    graph = StateGraph(AgentState)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("retrieve_one", retrieve_one_node)
    graph.add_node("grade", grade_node)
    graph.add_node("retry", bump_retry_node)
    graph.add_node("generate", generate_node)
    graph.add_node("verify", verify_node)

    graph.add_edge(START, "rewrite")
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
