from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from rank_bm25 import BM25Okapi

from backend.core.config import get_settings
from backend.rag.cache import cosine
from backend.rag.embeddings import get_embeddings
from backend.rag.rerank import rerank_pairwise
from backend.rag.store import dense_search, scroll_all_payloads

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _as_vector(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        inner = next(iter(value.values()), None)
        return _as_vector(inner)
    return [float(item) for item in value]


class Bm25Index:
    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []
        self._tokens: list[list[str]] = []
        self._bm25: BM25Okapi | None = None

    def rebuild(self, records: list[dict[str, Any]]) -> None:
        self._records = records
        self._tokens = [tokenize(record.get("text") or "") for record in records]
        self._bm25 = BM25Okapi(self._tokens) if self._tokens else None

    def search(
        self,
        query: str,
        *,
        k: int,
        plan_ids: set[str] | None,
        organization_ids: set[str] | None,
    ) -> list[dict[str, Any]]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
        hits: list[dict[str, Any]] = []
        for index in ranked:
            if scores[index] <= 0:
                continue
            record = self._records[index]
            if plan_ids and record.get("plan_id") not in plan_ids:
                continue
            if organization_ids and record.get("organization_id") not in organization_ids:
                continue
            hits.append(record)
            if len(hits) >= k:
                break
        return hits


_bm25 = Bm25Index()


def rebuild_bm25_from_qdrant() -> None:
    try:
        _bm25.rebuild(scroll_all_payloads())
    except Exception as exc:
        logger.warning("Could not rebuild BM25 index: %s", exc)
        _bm25.rebuild([])


def record_key(record: dict[str, Any]) -> str:
    return f"{record.get('document_id')}:{record.get('parent_id')}:{record.get('chunk_index')}"


def reciprocal_rank_fusion(
    dense_hits: list[dict[str, Any]],
    sparse_hits: list[dict[str, Any]],
    *,
    k: int = 60,
) -> list[dict[str, Any]]:
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}
    for rank, record in enumerate(dense_hits):
        key = record_key(record)
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        items[key] = record
    for rank, record in enumerate(sparse_hits):
        key = record_key(record)
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        items.setdefault(key, record)
    return [items[key] for key in sorted(scores, key=lambda item: scores[item], reverse=True)]


def mmr_select(
    query_vector: list[float],
    records: list[dict[str, Any]],
    *,
    k: int,
    lambda_mult: float = 0.5,
) -> list[dict[str, Any]]:
    if not records:
        return []
    if _as_vector(records[0].get("_vector")) is None:
        return records[:k]

    selected: list[dict[str, Any]] = []
    candidates = list(records)
    while candidates and len(selected) < k:
        if not selected:
            selected.append(candidates.pop(0))
            continue
        selected_vectors = [_as_vector(item["_vector"]) for item in selected]
        best_index = 0
        best_score = float("-inf")
        for index, candidate in enumerate(candidates):
            vector = _as_vector(candidate.get("_vector"))
            if vector is None:
                continue
            relevance = cosine(query_vector, vector)
            diversity = max(cosine(vector, chosen) for chosen in selected_vectors if chosen)
            score = lambda_mult * relevance - (1.0 - lambda_mult) * diversity
            if score > best_score:
                best_score = score
                best_index = index
        selected.append(candidates.pop(best_index))
    return selected


def expand_parents(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep child quotes for citations; expose parent_text for generation context."""
    seen_parents: set[str] = set()
    expanded: list[dict[str, Any]] = []
    for record in records:
        parent_id = record.get("parent_id") or record_key(record)
        if parent_id in seen_parents:
            continue
        seen_parents.add(parent_id)
        expanded.append(record)
    return expanded


def diversify_by_plan(
    records: list[dict[str, Any]],
    *,
    plan_ids: list[str] | None,
    k: int,
) -> list[dict[str, Any]]:
    """Prefer at least one chunk per scoped plan before filling remaining slots."""
    if k <= 0 or not records:
        return []
    if not plan_ids or len(plan_ids) <= 1:
        return records[:k]

    buckets: dict[str, list[dict[str, Any]]] = {plan_id: [] for plan_id in plan_ids}
    leftovers: list[dict[str, Any]] = []
    for record in records:
        plan_id = str(record.get("plan_id") or "")
        if plan_id in buckets:
            buckets[plan_id].append(record)
        else:
            leftovers.append(record)

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for plan_id in plan_ids:
        if len(selected) >= k or not buckets[plan_id]:
            continue
        record = buckets[plan_id].pop(0)
        key = record_key(record)
        selected.append(record)
        seen.add(key)

    while len(selected) < k:
        progressed = False
        for plan_id in plan_ids:
            if len(selected) >= k or not buckets[plan_id]:
                continue
            record = buckets[plan_id].pop(0)
            key = record_key(record)
            if key in seen:
                continue
            selected.append(record)
            seen.add(key)
            progressed = True
        if not progressed:
            break

    for record in leftovers:
        if len(selected) >= k:
            break
        key = record_key(record)
        if key in seen:
            continue
        selected.append(record)
        seen.add(key)

    return selected


def retrieve(
    query: str,
    *,
    plan_ids: list[UUID] | None = None,
    organization_ids: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    if plan_ids is not None and not plan_ids:
        return []

    settings = get_settings()
    plan_id_strs = [str(item) for item in plan_ids] if plan_ids else None
    org_id_strs = [str(item) for item in organization_ids] if organization_ids else None

    # Multi-plan scope: retrieve per plan so one insurer cannot crowd out the rest.
    if plan_id_strs and len(plan_id_strs) > 1:
        merged: dict[str, dict[str, Any]] = {}
        per_plan_k = max(3, settings.rag_dense_k // len(plan_id_strs) + 1)
        for plan_id in plan_id_strs:
            for hit in _retrieve_candidates(
                query,
                plan_id_strs=[plan_id],
                org_id_strs=org_id_strs,
                dense_k=per_plan_k,
                sparse_k=per_plan_k,
            ):
                merged[record_key(hit)] = hit
        expanded = expand_parents(list(merged.values()))
        pool_k = max(settings.rag_rerank_k * 2, len(plan_id_strs) * 2)
        reranked = rerank_pairwise(query, expanded, k=pool_k)
        return diversify_by_plan(reranked, plan_ids=plan_id_strs, k=settings.rag_rerank_k)

    expanded = _retrieve_candidates(
        query,
        plan_id_strs=plan_id_strs,
        org_id_strs=org_id_strs,
        dense_k=settings.rag_dense_k,
        sparse_k=settings.rag_sparse_k,
    )
    return rerank_pairwise(query, expanded, k=settings.rag_rerank_k)


class HybridRetriever:
    """Vector (Qdrant, cosine) + BM25 hybrid search with reciprocal-rank fusion, MMR
    diversification, and cross-encoder-pattern reranking. Thin named wrapper over
    `retrieve()` — the pipeline itself lives in the module-level functions above and is
    covered by `tests/test_rag_helpers.py`; this class just gives callers a clean,
    documented entry point.
    """

    def search(
        self,
        query: str,
        *,
        plan_ids: list[UUID] | None = None,
        organization_ids: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        return retrieve(query, plan_ids=plan_ids, organization_ids=organization_ids)


def _retrieve_candidates(
    query: str,
    *,
    plan_id_strs: list[str] | None,
    org_id_strs: list[str] | None,
    dense_k: int,
    sparse_k: int,
) -> list[dict[str, Any]]:
    settings = get_settings()
    query_vector = get_embeddings().embed_query(query)
    dense_hits = dense_search(
        query_vector,
        plan_ids=plan_id_strs,
        organization_ids=org_id_strs,
        limit=dense_k,
        score_threshold=settings.rag_score_threshold,
        with_vectors=True,
    )
    diverse = mmr_select(query_vector, dense_hits, k=dense_k)
    sparse_hits = _bm25.search(
        query,
        k=sparse_k,
        plan_ids=set(plan_id_strs) if plan_id_strs else None,
        organization_ids=set(org_id_strs) if org_id_strs else None,
    )
    fused = reciprocal_rank_fusion(diverse, sparse_hits)
    return expand_parents(fused)
