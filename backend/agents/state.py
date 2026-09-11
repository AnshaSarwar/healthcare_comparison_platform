from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from backend.rag.retriever import record_key

RouteKind = Literal["policy_qa", "compare", "refuse"]


class AgentMessage(TypedDict):
    role: str
    content: str


def merge_records(left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Reducer for parallel retrieve branches — dedupe by chunk key."""
    merged: dict[str, dict[str, Any]] = {}
    for record in (*(left or []), *(right or [])):
        merged[record_key(record)] = record
    return list(merged.values())


def append_unique_trace(
    left: list[dict[str, str]] | None,
    right: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    return [*(left or []), *(right or [])]


class AgentState(TypedDict, total=False):
    question: str
    plan_ids: list[str]
    organization_ids: list[str] | None
    route: RouteKind
    queries: list[str]
    active_query: str
    records: Annotated[list[dict[str, Any]], merge_records]
    retry_count: int
    max_retries: int
    comparison_facts: str
    comparison_summary: dict[str, Any] | None
    messages: list[AgentMessage]
    answer: str
    citations: list[dict[str, Any]]
    trace: Annotated[list[dict[str, str]], append_unique_trace]
    error: str | None
