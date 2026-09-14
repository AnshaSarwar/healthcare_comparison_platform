from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Iterator
from typing import Any, Literal
from uuid import UUID

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

RouteKind = Literal["policy_qa", "compare"]

# Shared zero-hallucination discipline, prepended to both route-specific prompts below.
# Health-plan cost-sharing figures and eligibility math have zero tolerance for
# fabrication — this block exists specifically to suppress two failure modes: (a) the
# model performing or "helpfully" simplifying arithmetic the sources don't already
# state, and (b) claims with no traceable source. Both prompts still forbid pricing
# separately below since that's a distinct compliance requirement, not a hallucination
# one — pricing must never appear even when it IS in a source.
RAG_STRICT_DISCIPLINE = (
    "You are a compliance-grade health-benefits policy assistant. Follow every rule exactly.\n\n"
    "SOURCE DISCIPLINE:\n"
    "1. Answer ONLY using the numbered sources provided. Do not use outside knowledge, "
    "training data, or assumptions about typical insurance plans.\n"
    "2. Every factual claim — every number, date, duration, percentage, and coverage rule — "
    "must be immediately followed by its source marker, e.g. [2]. A sentence with no bracket "
    "citation must contain no claim, only transition text.\n"
    "3. Quote numbers and durations VERBATIM from the source text. Never compute, convert, "
    "round, sum, average, or otherwise derive a number that is not already written explicitly "
    "in a source. If the answer requires arithmetic the sources do not already state as a "
    "result, say the plan documents do not state a computed answer.\n"
    "4. If sources conflict or are ambiguous, say so explicitly rather than silently picking one.\n"
    "5. If the sources do not contain the answer, respond exactly: "
    '"The provided plan documents do not state this." Do not guess or hedge with general '
    "insurance knowledge.\n"
    "6. Never invent a policy clause, exclusion, section name, or citation number not in the "
    "numbered sources.\n"
)

POLICY_SYSTEM_PROMPT = (
    RAG_STRICT_DISCIPLINE
    + "\nWhen multiple plans are in scope, answer separately for each plan — do not collapse "
    "different waiting periods or rules into a single number. "
    "Never mention premiums, prices, rate cards, or per-employee monthly cost, even if one "
    "appears in a source."
)

COMPARE_SYSTEM_PROMPT = (
    RAG_STRICT_DISCIPLINE
    + "\nCOMPARISON FACTS come from the deterministic rules engine — use them verbatim for "
    "eligibility outcomes, pass/fail/partial status, and ranking scores, without policy "
    "citations (they are not drawn from the numbered sources). Use numbered sources only for "
    "coverage wording (waiting periods, maternity, exclusions, pre-existing conditions). "
    "Never mention premiums, prices, rate cards, or per-employee monthly cost, even if one "
    "appears in a source. "
    "Write a concise comparison: lead with rules-engine ranking, then policy differences with "
    "[n] cites."
)

_POLICY_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", POLICY_SYSTEM_PROMPT),
        ("human", "{history_block}{facts}\n\nQuestion: {question}\n\nSources:\n{context}"),
    ]
)

_COMPARE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", COMPARE_SYSTEM_PROMPT),
        ("human", "{history_block}{facts}\n\nQuestion: {question}\n\nSources:\n{context}"),
    ]
)


def format_sources(records: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for index, record in enumerate(records, start=1):
        quote = (record.get("parent_text") or record.get("text") or "").strip()
        blocks.append(
            f"[{index}] Plan: {record.get('plan_name')} | Section: {record.get('section')}\n{quote}"
        )
    return "\n\n".join(blocks) if blocks else "(no sources)"


def format_history(messages: list[dict[str, str]] | None) -> str:
    if not messages:
        return ""
    lines = ["Recent conversation:"]
    for item in messages[-6:]:
        role = item.get("role", "user")
        content = (item.get("content") or "").strip()
        if content:
            lines.append(f"- {role}: {content}")
    return "\n".join(lines) + "\n\n"


def citations_from_answer(answer: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cited = {int(number) for number in re.findall(r"\[(\d+)\]", answer)}
    citations: list[dict[str, Any]] = []
    for number in sorted(cited):
        if not 1 <= number <= len(records):
            continue
        record = records[number - 1]
        try:
            plan_id = UUID(str(record["plan_id"]))
            document_id = UUID(str(record["document_id"]))
        except (KeyError, ValueError):
            continue
        quote = (record.get("text") or "")[:280]
        citations.append(
            {
                "plan_id": str(plan_id),
                "plan_name": record.get("plan_name") or "",
                "section": record.get("section") or "",
                "quote": quote,
                "document_id": str(document_id),
                "page_number": record.get("page_number"),
            }
        )
    return citations


def sources_from_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the metadata-first SSE "sources" payload: one entry per retrieved/reranked
    record, 1-indexed to match the exact `[n]` numbering `format_sources` uses for the
    generation prompt above. Emitted before the token stream starts — unlike
    `citations_from_answer`, this doesn't depend on the model having generated anything
    yet, since it just describes what the answer will be grounded on.
    """
    return [
        {
            "index": index,
            "plan_id": record.get("plan_id"),
            "plan_name": record.get("plan_name"),
            "section": record.get("section"),
            "document_id": record.get("document_id"),
            "chunk_index": record.get("chunk_index"),
            "page_number": record.get("page_number"),
            "score": record.get("_score"),
        }
        for index, record in enumerate(records, start=1)
    ]


def _llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.ollama_chat_model,
        api_key=settings.openai_api_key or None,
        base_url=settings.ollama_base_url or None,
        temperature=0,
    )


def _chain(route: RouteKind):
    prompt = _COMPARE_PROMPT if route == "compare" else _POLICY_PROMPT
    return prompt | _llm() | StrOutputParser()


def _payload(
    question: str,
    records: list[dict[str, Any]],
    *,
    facts: str = "",
    route: RouteKind = "policy_qa",
    messages: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    return {
        "history_block": format_history(messages),
        "facts": facts or "COMPARISON FACTS: none.",
        "question": question,
        "context": format_sources(records),
    }


def generate_answer(
    question: str,
    records: list[dict[str, Any]],
    facts: str = "",
    *,
    route: RouteKind = "policy_qa",
    messages: list[dict[str, str]] | None = None,
) -> str:
    chain = _chain(route)
    return chain.invoke(_payload(question, records, facts=facts, route=route, messages=messages))


def stream_answer(
    question: str,
    records: list[dict[str, Any]],
    facts: str = "",
    *,
    route: RouteKind = "policy_qa",
    messages: list[dict[str, str]] | None = None,
) -> Iterator[str]:
    chain = _chain(route)
    for chunk in chain.stream(_payload(question, records, facts=facts, route=route, messages=messages)):
        if chunk:
            yield chunk


async def astream_answer(
    question: str,
    records: list[dict[str, Any]],
    facts: str = "",
    *,
    route: RouteKind = "policy_qa",
    messages: list[dict[str, str]] | None = None,
) -> AsyncIterator[str]:
    chain = _chain(route)
    async for chunk in chain.astream(
        _payload(question, records, facts=facts, route=route, messages=messages)
    ):
        if chunk:
            yield chunk
