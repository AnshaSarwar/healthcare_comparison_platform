"""LangGraph agentic RAG for Benefits Compare (no Graph RAG).

Supervisor routes to policy or compare subgraphs. Tools wrap hybrid retrieve
and the deterministic rules engine; Redis stores multi-turn thread messages.
"""

from backend.agents.graph import build_benefits_agent_graph, get_benefits_agent
from backend.agents.tools import BENEFITS_TOOLS

__all__ = ["BENEFITS_TOOLS", "build_benefits_agent_graph", "get_benefits_agent"]
