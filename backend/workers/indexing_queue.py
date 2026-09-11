from __future__ import annotations

import logging
from uuid import UUID

from backend.rag.cache import get_redis

logger = logging.getLogger(__name__)

QUEUE_KEY = "index:jobs"


def enqueue_document(document_id: UUID) -> bool:
    client = get_redis()
    if client is None:
        return False
    client.rpush(QUEUE_KEY, str(document_id))
    return True


def dequeue_document(timeout_seconds: int = 5) -> UUID | None:
    client = get_redis()
    if client is None:
        return None
    item = client.blpop(QUEUE_KEY, timeout=timeout_seconds)
    if not item:
        return None
    _, raw = item
    try:
        return UUID(str(raw))
    except ValueError:
        logger.warning("Invalid index job id: %s", raw)
        return None


def queue_depth() -> int:
    client = get_redis()
    if client is None:
        return 0
    return int(client.llen(QUEUE_KEY))
