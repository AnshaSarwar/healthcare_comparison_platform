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

POLICY_SYSTEM_PROMPT = (
    "You are a group-health benefits assistant. Answer only from the numbered sources. "
    "Cite sources with [n] immediately after each claim. "
    "If the sources cover multiple plans, answer separately for each plan — "
    "do not collapse different waiting periods or rules into a single number. "
    "If the sources do not contain the answer, say you cannot find it in the policy wording. "
    "Never mention premiums, prices, rate cards, or per-employee monthly cost. "
    "Never invent clauses."
)

COMPARE_SYSTEM_PROMPT = (
    "You are a group-health benefits assistant comparing employer plans. "
    "COMPARISON FACTS come from the deterministic rules engine — use them for eligibility "
    "outcomes, pass/fail/partial status, and ranking scores without policy citations. "
    "Use numbered sources only for coverage wording (waiting periods, maternity, exclusions, "
    "pre-existing conditions). "
    "Never mention premiums, prices, rate cards, or per-employee monthly cost. "
    "Never invent clauses. "
    "Write a concise comparison: lead with rules-engine ranking, then policy differences with [n] cites."
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
            }
        )
    return citations


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
