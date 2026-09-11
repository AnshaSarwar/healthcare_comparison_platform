from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

_RERANK_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You rerank retrieved health-plan policy clauses. "
            'Return JSON only: {{"order": [int, ...]}} with the most relevant passage indices first. '
            "Use only the provided indices.",
        ),
        (
            "human",
            "Question:\n{question}\n\nPassages:\n{passages}\n\n"
            "Return at most {k} indices, best first.",
        ),
    ]
)


def _parse_order(text: str, size: int) -> list[int]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    order: list[int] = []
    if match:
        try:
            data = json.loads(match.group(0))
            order = [int(item) for item in data.get("order", [])]
        except (json.JSONDecodeError, TypeError, ValueError):
            order = []
    if not order:
        order = [int(item) for item in re.findall(r"\d+", text)]
    return [index for index in order if 0 <= index < size]


def rerank(question: str, records: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    if len(records) <= k:
        return records

    settings = get_settings()
    passages = "\n\n".join(
        f"[{index}] Plan={record.get('plan_name')} Section={record.get('section')}\n"
        f"{(record.get('text') or '')[:500]}"
        for index, record in enumerate(records)
    )
    llm = ChatOpenAI(
        model=settings.ollama_chat_model,
        api_key=settings.openai_api_key or None,
        base_url=settings.ollama_base_url or None,
        temperature=0,
    )
    chain = _RERANK_PROMPT | llm
    try:
        message = chain.invoke({"question": question, "passages": passages, "k": k})
        content = message.content if hasattr(message, "content") else str(message)
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block) for block in content
            )
        order = _parse_order(str(content), len(records))
    except Exception as exc:
        logger.warning("LLM rerank failed, using fused order: %s", exc)
        return records[:k]

    seen: set[int] = set()
    ranked: list[dict[str, Any]] = []
    for index in order:
        if index in seen:
            continue
        seen.add(index)
        ranked.append(records[index])
        if len(ranked) >= k:
            return ranked
    for index, record in enumerate(records):
        if index not in seen:
            ranked.append(record)
        if len(ranked) >= k:
            break
    return ranked
