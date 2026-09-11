"""Domain tools for the Benefits agent.

LangChain tool wrappers over retrieve + rules-engine compare.
The graph invokes these as mandatory steps (not an open ReAct loop):
compare always runs run_comparison before narrative retrieve.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg, tool

RetrieveFn = Callable[[str, list[UUID] | None, list[UUID] | None], list[dict[str, Any]]]
CompareFn = Callable[[list[UUID]], tuple[str, dict[str, Any]]]


def _cfg(config: RunnableConfig | None) -> dict[str, Any]:
    if not config:
        return {}
    return dict(config.get("configurable") or {})


@tool("retrieve_policy")
def retrieve_policy_tool(
    query: str,
    plan_ids: list[str],
    organization_ids: list[str] | None = None,
    *,
    config: Annotated[RunnableConfig, InjectedToolArg],
) -> list[dict[str, Any]]:
    """Retrieve policy booklet passages for a search query (hybrid RAG)."""
    retrieve_fn: RetrieveFn | None = _cfg(config).get("retrieve_fn")
    if retrieve_fn is None:
        raise RuntimeError("retrieve_fn is not configured")
    plans = [UUID(item) for item in plan_ids] if plan_ids else None
    orgs = [UUID(item) for item in organization_ids] if organization_ids else None
    return retrieve_fn(query, plans, orgs)


@tool("run_comparison")
def run_comparison_tool(
    plan_ids: list[str],
    *,
    config: Annotated[RunnableConfig, InjectedToolArg],
) -> dict[str, Any]:
    """Run the deterministic eligibility/scoring rules engine for the given plans."""
    compare_fn: CompareFn | None = _cfg(config).get("compare_fn")
    if compare_fn is None:
        raise RuntimeError("compare_fn is not configured for this user")
    facts, summary = compare_fn([UUID(item) for item in plan_ids])
    return {"facts": facts, "summary": summary}


BENEFITS_TOOLS = [retrieve_policy_tool, run_comparison_tool]
