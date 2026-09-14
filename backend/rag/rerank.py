from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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

_PAIRWISE_SCORE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You score how relevant ONE passage is to ONE question, in isolation from any "
            "other passage. Return JSON only: {{\"score\": <float 0.0-1.0>}}. "
            "1.0 = directly answers the question; 0.0 = unrelated.",
        ),
        (
            "human",
            "Question:\n{question}\n\nPassage:\n{passage}",
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


def _parse_score(text: str) -> float | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return max(0.0, min(1.0, float(data.get("score"))))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    match = re.search(r"-?\d*\.\d+|\d+", text)
    if match:
        try:
            return max(0.0, min(1.0, float(match.group(0))))
        except ValueError:
            return None
    return None


def _score_one(question: str, record: dict[str, Any]) -> float | None:
    settings = get_settings()
    passage = f"Plan={record.get('plan_name')} Section={record.get('section')}\n{(record.get('text') or '')[:500]}"
    llm = ChatOpenAI(
        model=settings.ollama_chat_model,
        api_key=settings.openai_api_key or None,
        base_url=settings.ollama_base_url or None,
        temperature=0,
    )
    chain = _PAIRWISE_SCORE_PROMPT | llm
    try:
        message = chain.invoke({"question": question, "passage": passage})
        content = message.content if hasattr(message, "content") else str(message)
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block) for block in content
            )
        return _parse_score(str(content))
    except Exception as exc:
        logger.warning("Pairwise rerank score failed for one candidate: %s", exc)
        return None


def rerank_pairwise(question: str, records: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    """Cross-encoder-pattern reranker: score(query, passage) independently per candidate,
    then sort by score — unlike the listwise `rerank()` above, which asks the LLM for one
    combined ordering over all passages in a single call.

    Scoring calls run concurrently (they're network-bound Ollama requests) since this
    issues one call per candidate rather than one call total. A candidate whose scoring
    call fails (timeout, malformed response) keeps its incoming fused-order rank rather
    than being dropped — same fallback philosophy as `rerank()`.
    """
    if len(records) <= k:
        return records

    scores: list[float | None] = [None] * len(records)
    with ThreadPoolExecutor(max_workers=min(6, len(records))) as pool:
        futures = {
            pool.submit(_score_one, question, record): index
            for index, record in enumerate(records)
        }
        for future in as_completed(futures):
            scores[futures[future]] = future.result()

    def sort_key(index: int) -> tuple[float, int]:
        score = scores[index]
        if score is None:
            # Unscored candidates keep their fused-order position relative to each
            # other, ranked below every successfully-scored candidate.
            return (-1.0, -index)
        return (score, -index)

    order = sorted(range(len(records)), key=sort_key, reverse=True)
    return [records[index] for index in order[:k]]
