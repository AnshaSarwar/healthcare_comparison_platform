from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from functools import partial
from uuid import UUID

from backend.core.policies import SecurityContext
from backend.rag.cache import get_exact_cached_answer, get_semantic_cached_answer, store_cached_answer
from backend.rag.embeddings import get_embeddings
from backend.rag.generate import astream_answer, citations_from_answer, sources_from_records
from backend.rag.retriever import retrieve
from backend.rag.store import rag_configured
from backend.schemas import Citation, RagQueryResponse

logger = logging.getLogger(__name__)


class RagServiceError(Exception):
    pass


def _plan_id_strs(plan_ids: list[UUID]) -> list[str]:
    return [str(plan_id) for plan_id in plan_ids]


def _to_response(payload: dict, *, cached: bool) -> RagQueryResponse:
    citations = [Citation.model_validate(item) for item in payload.get("citations", [])]
    return RagQueryResponse(
        answer=payload.get("answer") or "",
        citations=citations,
        cached=cached,
    )


def lookup_cached_answer(
    ctx: SecurityContext,
    plan_ids: list[UUID],
    question: str,
) -> RagQueryResponse | None:
    plan_keys = _plan_id_strs(plan_ids)
    exact = get_exact_cached_answer(ctx.organization_id, ctx.role.value, plan_keys, question)
    if exact:
        return _to_response(exact, cached=True)
    try:
        embedding = get_embeddings().embed_query(question)
    except Exception:
        return None
    semantic = get_semantic_cached_answer(
        ctx.organization_id, ctx.role.value, plan_keys, embedding
    )
    if semantic:
        return _to_response(semantic, cached=True)
    return None


async def stream_rag_answer(
    ctx: SecurityContext,
    question: str,
    plan_ids: list[UUID],
    organization_ids: list[UUID] | None,
) -> AsyncIterator[str]:
    if not rag_configured():
        raise RagServiceError("RAG is not configured")

    cached = lookup_cached_answer(ctx, plan_ids, question)
    if cached is not None:
        yield _sse({"type": "final", **cached.model_dump(mode="json")})
        return

    try:
        records = await asyncio.to_thread(
            partial(retrieve, question, plan_ids=plan_ids, organization_ids=organization_ids)
        )
    except Exception as exc:
        logger.exception("Retrieval failed")
        yield _sse({"type": "error", "detail": f"Retrieval failed: {exc}"})
        return

    yield _sse({"type": "sources", "sources": sources_from_records(records)})

    pieces: list[str] = []
    async for token in astream_answer(question, records):
        pieces.append(token)
        yield _sse({"type": "token", "text": token})

    answer = "".join(pieces)
    citations = citations_from_answer(answer, records)
    payload = {"answer": answer, "citations": citations, "cached": False}
    try:
        embedding = get_embeddings().embed_query(question)
        store_cached_answer(
            ctx.organization_id,
            ctx.role.value,
            _plan_id_strs(plan_ids),
            question,
            embedding,
            {"answer": answer, "citations": citations},
        )
    except Exception:
        logger.warning("Failed to store RAG response cache", exc_info=True)
    yield _sse({"type": "final", **payload})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
