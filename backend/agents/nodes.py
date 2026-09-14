from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.types import Send

from backend.agents.routing import grade_records, rewrite_queries, route_question
from backend.agents.state import AgentMessage, AgentState
from backend.agents.tools import retrieve_policy_tool, run_comparison_tool
from backend.observability.agent_trace import log_agent_event
from backend.rag.generate import citations_from_answer, sources_from_records, stream_answer

logger = logging.getLogger(__name__)

_PRICING_LEAK = re.compile(
    r"("
    r"\bmonthly\s+premiums?\b|"
    r"\bpremiums?\s+per\s+employee\b|"
    r"\brate\s*cards?\b|"
    r"\bper[- ]employee\s+(monthly\s+)?(costs?|premiums?)\b|"
    r"\bmonthly cost\b|"
    r"\bpricing tier\b|"
    r"\$\d+"
    r")",
    re.IGNORECASE,
)


_HAS_NUMBER = re.compile(r"\d")
_HAS_CITATION = re.compile(r"\[\d+\]")


def _find_unattributed_numbers(answer: str) -> list[str]:
    """Observability only — flags sentences with a number but no [n] citation marker
    anywhere in them, for the structured agent log. Never mutates the answer: unlike
    the pricing-leak check above, a false positive here (e.g. a transition sentence
    referencing "two plans") is common enough that auto-rewriting would do more harm
    than a logged warning a reviewer can act on.
    """
    sentences = re.split(r"(?<=[.!?])\s+", answer)
    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
        and _HAS_NUMBER.search(sentence)
        and not _HAS_CITATION.search(sentence)
    ]


def _append_trace_item(node: str, detail: str) -> list[dict[str, str]]:
    return [{"node": node, "detail": detail}]


def _prior_messages(state: AgentState) -> list[AgentMessage]:
    return list(state.get("messages") or [])


def route_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    route = route_question(state["question"])
    messages = _prior_messages(state)
    messages.append({"role": "user", "content": state["question"]})
    log_agent_event("route", route, question_len=len(state["question"]))
    return {
        "route": route,
        "retry_count": 0,
        "queries": [state["question"]],
        "records": [],
        "comparison_facts": "",
        "comparison_summary": None,
        "messages": messages,
        "answer": "",
        "citations": [],
        "error": None,
        "trace": _append_trace_item("route", route),
    }


def rewrite_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    queries = rewrite_queries(state["question"])
    retry = int(state.get("retry_count") or 0)
    detail = f"queries={len(queries)};retry={retry}"
    log_agent_event("rewrite", detail, queries=queries)
    return {
        "queries": queries,
        "trace": _append_trace_item("rewrite", detail),
    }


def fanout_retrieves(state: AgentState) -> list[Send]:
    """Parallel multi-query retrieve — each rewritten query is its own branch."""
    queries = state.get("queries") or [state["question"]]
    return [
        Send(
            "retrieve_one",
            {
                "active_query": query,
                "question": state["question"],
                "plan_ids": state.get("plan_ids") or [],
                "organization_ids": state.get("organization_ids"),
                "route": state.get("route"),
                "retry_count": state.get("retry_count") or 0,
                "max_retries": state.get("max_retries") or 1,
                "comparison_facts": state.get("comparison_facts") or "",
                "comparison_summary": state.get("comparison_summary"),
                "messages": state.get("messages") or [],
                "records": [],
                "trace": [],
            },
        )
        for query in queries
    ]


def retrieve_one_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    query = state.get("active_query") or state["question"]
    plan_ids = list(state.get("plan_ids") or [])
    org_ids = state.get("organization_ids")
    try:
        hits = retrieve_policy_tool.invoke(
            {
                "query": query,
                "plan_ids": plan_ids,
                "organization_ids": org_ids,
            },
            config=config,
        )
    except Exception as exc:
        logger.exception("retrieve_policy tool failed")
        log_agent_event("retrieve", "error", error=str(exc), query=query)
        return {
            "records": [],
            "error": f"retrieve failed: {exc}",
            "trace": _append_trace_item("retrieve", f"error:{query[:40]}"),
        }
    log_agent_event("retrieve", f"hits={len(hits)}", query=query, hit_count=len(hits))
    return {
        "records": hits,
        "trace": _append_trace_item("retrieve", f"hits={len(hits)};q={query[:40]}"),
    }


def grade_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    before = len(state.get("records") or [])
    original = list(state.get("records") or [])
    graded = grade_records(state["question"], original)
    graded_plans = {str(record.get("plan_id") or "") for record in graded}
    for record in original:
        plan_id = str(record.get("plan_id") or "")
        if not plan_id or plan_id in graded_plans:
            continue
        graded.append(record)
        graded_plans.add(plan_id)
    log_agent_event("grade", f"kept={len(graded)}", before=before, after=len(graded))
    return {
        "records": graded,
        "trace": _append_trace_item("grade", f"kept={len(graded)}"),
    }


def bump_retry_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    retry = int(state.get("retry_count") or 0) + 1
    log_agent_event("retry", f"retry={retry}")
    return {
        "retry_count": retry,
        "trace": _append_trace_item("retry", f"retry={retry}"),
    }


def compare_tool_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Mandatory rules-engine step for compare route — never optional LLM choice."""
    plan_ids = list(state.get("plan_ids") or [])
    try:
        payload = run_comparison_tool.invoke({"plan_ids": plan_ids}, config=config)
        facts = str(payload.get("facts") or "")
        summary = payload.get("summary")
        log_agent_event(
            "compare",
            "ok",
            plan_count=len((summary or {}).get("outcomes", [])),
            ranking=(summary or {}).get("ranking"),
        )
        return {
            "comparison_facts": facts,
            "comparison_summary": summary,
            "trace": _append_trace_item("compare", "ok"),
        }
    except Exception as exc:
        logger.exception("run_comparison tool failed")
        log_agent_event("compare", "error", error=str(exc))
        return {
            "comparison_facts": "COMPARISON FACTS: comparison failed.",
            "comparison_summary": None,
            "error": str(exc),
            "trace": _append_trace_item("compare", "error"),
        }


def generate_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    question = state["question"]
    records = state.get("records") or []
    facts = state.get("comparison_facts") or "COMPARISON FACTS: none."
    route = state.get("route") or "policy_qa"
    history = _prior_messages(state)[:-1]

    if route == "refuse":
        answer = (
            "I can only help with group health plan policy questions and employer plan comparisons."
        )
        return {
            "answer": answer,
            "citations": [],
            "trace": _append_trace_item("generate", "refuse"),
        }
    if not records and route == "policy_qa":
        answer = "I cannot find that in the indexed policy wording for the selected plans."
        return {
            "answer": answer,
            "citations": [],
            "trace": _append_trace_item("generate", "no_context"),
        }

    gen_route = "compare" if route == "compare" else "policy_qa"
    writer = get_stream_writer()
    writer({"type": "sources", "sources": sources_from_records(records)})
    pieces: list[str] = []
    try:
        for chunk in stream_answer(
            question,
            records,
            facts=facts,
            route=gen_route,
            messages=history,
        ):
            pieces.append(chunk)
            writer({"type": "token", "text": chunk})
        answer = "".join(pieces)
    except Exception as exc:
        logger.exception("Agent generate failed")
        log_agent_event("generate", "error", error=str(exc))
        return {
            "answer": "I could not generate an answer right now.",
            "citations": [],
            "error": str(exc),
            "trace": _append_trace_item("generate", "error"),
        }

    log_agent_event("generate", "ok", route=gen_route, chars=len(answer))
    leak = "pricing_leak" if _PRICING_LEAK.search(answer) else "clean"
    return {
        "answer": answer,
        "trace": _append_trace_item("generate", f"chars={len(answer)};{leak}"),
    }


def verify_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    answer = state.get("answer") or ""
    records = state.get("records") or []
    detail = "ok"
    if _PRICING_LEAK.search(answer):
        sentences = re.split(r"(?<=[.!?])\s+", answer)
        cleaned = [
            sentence.strip()
            for sentence in sentences
            if sentence.strip() and not _PRICING_LEAK.search(sentence)
        ]
        if cleaned:
            answer = " ".join(cleaned)
            detail = "pricing_sentences_removed"
        elif state.get("route") == "compare" and state.get("comparison_summary"):
            outcomes = state["comparison_summary"].get("outcomes") or []
            lines = [
                "Eligibility comparison from the rules engine (coverage terms only; pricing omitted):"
            ]
            for row in outcomes:
                lines.append(
                    f"- {row.get('plan_name')}: outcome={row.get('overall_outcome')}, "
                    f"score={row.get('total_score')}"
                )
            answer = "\n".join(lines)
            detail = "pricing_blocked_compare_fallback"
        else:
            answer = (
                "I can discuss coverage terms and eligibility outcomes, but not premiums or pricing. "
                "Ask about waiting periods, exclusions, maternity, or pre-existing condition rules."
            )
            detail = "pricing_blocked"

    citations = citations_from_answer(answer, records) if records else []
    unattributed = _find_unattributed_numbers(answer)
    if unattributed:
        log_agent_event(
            "verify",
            "unattributed_numbers_detected",
            count=len(unattributed),
            examples=unattributed[:3],
        )
    messages = _prior_messages(state)
    messages.append({"role": "assistant", "content": answer})
    log_agent_event("verify", detail, citation_count=len(citations))
    return {
        "answer": answer,
        "citations": citations,
        "messages": messages,
        "trace": _append_trace_item("verify", detail),
    }


def refuse_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    answer = (
        "I can only help with group health plan policy questions and employer plan comparisons."
    )
    messages = _prior_messages(state)
    messages.append({"role": "assistant", "content": answer})
    return {
        "answer": answer,
        "citations": [],
        "messages": messages,
        "trace": _append_trace_item("refuse", "out_of_scope"),
    }


def after_grade_decision(state: AgentState) -> str:
    records = state.get("records") or []
    facts = (state.get("comparison_facts") or "").strip()
    has_usable_facts = (
        bool(facts)
        and "unavailable" not in facts.lower()
        and "failed" not in facts.lower()
        and facts != "COMPARISON FACTS: none."
    )
    retry = int(state.get("retry_count") or 0)
    max_retries = int(state.get("max_retries") or 1)
    if not records and not has_usable_facts and retry < max_retries:
        return "retry"
    return "generate"


def after_route_decision(state: AgentState) -> str:
    route = state.get("route") or "policy_qa"
    if route == "compare":
        return "compare"
    if route == "refuse":
        return "refuse"
    return "policy"
