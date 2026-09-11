from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from backend.agents.checkpointer import get_checkpointer
from backend.agents.nodes import after_route_decision, refuse_node, route_node
from backend.agents.state import AgentState
from backend.agents.subgraphs.compare import build_compare_subgraph
from backend.agents.subgraphs.policy import build_policy_subgraph


def build_benefits_agent_graph(*, with_memory: bool = True):
    """Supervisor graph: route → policy subgraph | compare subgraph | refuse.

    Why this shape for Benefits Compare:
    - Policy Q&A needs a grounded CRAG pipeline (not free-form tool loops).
    - Compare must always run the rules engine before narrative retrieve.
    - Subgraphs keep those contracts separate and testable.
    """
    graph = StateGraph(AgentState)
    graph.add_node("route", route_node)
    graph.add_node("policy", build_policy_subgraph())
    graph.add_node("compare", build_compare_subgraph())
    graph.add_node("refuse", refuse_node)

    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        after_route_decision,
        {"policy": "policy", "compare": "compare", "refuse": "refuse"},
    )
    graph.add_edge("policy", END)
    graph.add_edge("compare", END)
    graph.add_edge("refuse", END)

    if with_memory:
        return graph.compile(checkpointer=get_checkpointer())
    return graph.compile()


@lru_cache
def get_benefits_agent():
    # Fresh run per turn; multi-turn history is Redis thread messages, not graph checkpoints.
    # Avoids reducer pollution of records/trace across employer questions.
    return build_benefits_agent_graph(with_memory=False)
