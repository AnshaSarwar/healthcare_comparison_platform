from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

import redis

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None
_client_failed = False


def get_redis() -> redis.Redis | None:
    global _client, _client_failed
    if _client is not None:
        return _client
    if _client_failed:
        return None
    try:
        client = redis.from_url(get_settings().redis_url, decode_responses=True)
        client.ping()
        _client = client
        return _client
    except Exception as exc:
        _client_failed = True
        logger.warning("Redis unavailable; RAG caches disabled: %s", exc)
        return None


def _plan_key(plan_ids: list[str] | None) -> str:
    if not plan_ids:
        return "all"
    return ",".join(sorted(plan_ids))


def exact_answer_key(org_id: UUID, role: str, plan_ids: list[str], question: str) -> str:
    digest = hashlib.sha256(question.strip().lower().encode()).hexdigest()
    return f"rag:exact:{org_id}:{role}:{_plan_key(plan_ids)}:{digest}"


def semantic_list_key(org_id: UUID, role: str, plan_ids: list[str]) -> str:
    return f"rag:sem:{org_id}:{role}:{_plan_key(plan_ids)}"


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm_l = sum(a * a for a in left) ** 0.5
    norm_r = sum(b * b for b in right) ** 0.5
    if norm_l == 0 or norm_r == 0:
        return 0.0
    return dot / (norm_l * norm_r)


def get_exact_cached_answer(org_id: UUID, role: str, plan_ids: list[str], question: str) -> dict | None:
    client = get_redis()
    if client is None:
        return None
    raw = client.get(exact_answer_key(org_id, role, plan_ids, question))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def get_semantic_cached_answer(
    org_id: UUID,
    role: str,
    plan_ids: list[str],
    question_embedding: list[float],
) -> dict | None:
    client = get_redis()
    if client is None:
        return None
    threshold = get_settings().rag_semantic_cache_threshold
    raw_items = client.lrange(semantic_list_key(org_id, role, plan_ids), 0, 49)
    best: tuple[float, dict] | None = None
    for raw in raw_items:
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        embedding = item.get("embedding")
        payload = item.get("payload")
        if not embedding or not payload:
            continue
        score = cosine(question_embedding, embedding)
        if score >= threshold and (best is None or score > best[0]):
            best = (score, payload)
    return None if best is None else best[1]


def store_cached_answer(
    org_id: UUID,
    role: str,
    plan_ids: list[str],
    question: str,
    question_embedding: list[float],
    payload: dict[str, Any],
) -> None:
    client = get_redis()
    if client is None:
        return
    encoded = json.dumps(payload)
    client.set(exact_answer_key(org_id, role, plan_ids, question), encoded, ex=60 * 60 * 12)
    list_key = semantic_list_key(org_id, role, plan_ids)
    client.lpush(
        list_key,
        json.dumps({"embedding": question_embedding, "payload": payload}),
    )
    client.ltrim(list_key, 0, 49)
    client.expire(list_key, 60 * 60 * 12)
