"""Durable multi-turn chat memory in Redis (survives API restarts).

MemorySaver only covers in-process graph execution; employer threads need
cross-restart persistence for the messages list.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.rag.cache import get_redis

logger = logging.getLogger(__name__)

_TTL_SECONDS = 60 * 60 * 24 * 7


def _key(thread_id: str, org_id: str) -> str:
    return f"agent:thread:{org_id}:{thread_id}:messages"


def load_thread_messages(thread_id: str, org_id: str) -> list[dict[str, str]]:
    client = get_redis()
    if client is None:
        return []
    raw = client.get(_key(thread_id, org_id))
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [
        {"role": str(item.get("role", "user")), "content": str(item.get("content", ""))}
        for item in data
        if isinstance(item, dict) and item.get("content")
    ]


def save_thread_messages(thread_id: str, org_id: str, messages: list[dict[str, Any]]) -> None:
    client = get_redis()
    if client is None:
        return
    trimmed = messages[-20:]
    client.set(_key(thread_id, org_id), json.dumps(trimmed), ex=_TTL_SECONDS)
