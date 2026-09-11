from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from backend.agents.state import RouteKind
from backend.core.config import get_settings

logger = logging.getLogger(__name__)

_COMPARE_HINTS = (
    "compare",
    "comparison",
    "rank",
    "ranking",
    "which plan",
    "best plan",
    "eligible",
    "eligibility",
    "score the",
    "vs",
    "versus",
)
_REFUSE_HINTS = (
    "write malware",
    "hack into",
    "steal password",
    "ignore previous instructions",
)

_ROUTE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Classify the user message for a group-health benefits assistant. "
            'Return JSON only: {{"route": "policy_qa"|"compare"|"refuse"}}. '
            "policy_qa = questions about policy wording (waiting periods, maternity, exclusions). "
            "compare = rank/compare plans or eligibility against employer requirements. "
            "refuse = unsafe, off-topic, or unrelated to benefits plans.",
        ),
        ("human", "{question}"),
    ]
)

_REWRITE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Rewrite the employer benefits question into up to 3 short search queries "
            "for policy booklet retrieval. Return JSON only: "
            '{{"queries": ["...", "..."]}}. Keep domain terms (maternity, waiting period, '
            "pre-existing, exclusion). Do not mention premiums or prices.",
        ),
        ("human", "{question}"),
    ]
)

_GRADE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Grade retrieved policy passages for relevance to the question. "
            'Return JSON only: {{"relevant": [int, ...]}} using the passage indices. '
            "Include only passages that help answer the question. "
            "When several plans appear, keep at least one relevant passage per plan "
            "if that plan's wording addresses the question (including explicit 'not covered').",
        ),
        (
            "human",
            "Question:\n{question}\n\nPassages:\n{passages}\n",
        ),
    ]
)


def _llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.ollama_chat_model,
        api_key=settings.openai_api_key or None,
        base_url=settings.ollama_base_url or None,
        temperature=0,
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def heuristic_route(question: str) -> RouteKind:
    lowered = question.lower().strip()
    if not lowered:
        return "refuse"
    if any(hint in lowered for hint in _REFUSE_HINTS):
        return "refuse"
    if any(hint in lowered for hint in _COMPARE_HINTS):
        return "compare"
    return "policy_qa"


def route_question(question: str) -> RouteKind:
    fallback = heuristic_route(question)
    settings = get_settings()
    if not settings.openai_api_key.strip():
        return fallback
    try:
        message = (_ROUTE_PROMPT | _llm()).invoke({"question": question})
        content = message.content if hasattr(message, "content") else str(message)
        route = str(_parse_json_object(str(content)).get("route", "")).strip()
        if route in {"policy_qa", "compare", "refuse"}:
            return route  # type: ignore[return-value]
    except Exception as exc:
        logger.warning("LLM route failed, using heuristic: %s", exc)
    return fallback


def rewrite_queries(question: str) -> list[str]:
    settings = get_settings()
    if not settings.openai_api_key.strip():
        return [question]
    try:
        message = (_REWRITE_PROMPT | _llm()).invoke({"question": question})
        content = message.content if hasattr(message, "content") else str(message)
        queries = _parse_json_object(str(content)).get("queries", [])
        cleaned = [str(item).strip() for item in queries if str(item).strip()]
        if cleaned:
            return cleaned[:3]
    except Exception as exc:
        logger.warning("LLM rewrite failed: %s", exc)
    return [question]


def grade_records(question: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not records:
        return []
    settings = get_settings()
    if not settings.openai_api_key.strip():
        return _heuristic_grade(question, records)

    passages = "\n\n".join(
        f"[{index}] Plan={record.get('plan_name')} Section={record.get('section')}\n"
        f"{(record.get('text') or record.get('parent_text') or '')[:400]}"
        for index, record in enumerate(records)
    )
    try:
        message = (_GRADE_PROMPT | _llm()).invoke({"question": question, "passages": passages})
        content = message.content if hasattr(message, "content") else str(message)
        relevant = _parse_json_object(str(content)).get("relevant", [])
        indices: list[int] = []
        for item in relevant:
            try:
                indices.append(int(item))
            except (TypeError, ValueError):
                continue
        graded = [records[index] for index in indices if 0 <= index < len(records)]
        if graded:
            return graded
    except Exception as exc:
        logger.warning("LLM grade failed: %s", exc)
    return _heuristic_grade(question, records)


def _heuristic_grade(question: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tokens = {token for token in re.findall(r"[a-z0-9]+", question.lower()) if len(token) > 2}
    if not tokens:
        return records
    scored: list[tuple[int, dict[str, Any]]] = []
    for record in records:
        text = f"{record.get('section') or ''} {record.get('text') or ''} {record.get('parent_text') or ''}".lower()
        overlap = sum(1 for token in tokens if token in text)
        if overlap > 0:
            scored.append((overlap, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [record for _, record in scored] or records
