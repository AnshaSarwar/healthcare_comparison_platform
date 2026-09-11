from __future__ import annotations

import logging
import uuid
from typing import Any
from uuid import UUID

from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None


def rag_configured() -> bool:
    return bool(get_settings().openai_api_key.strip())


def get_qdrant() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=get_settings().qdrant_url)
    return _client


def ensure_collection() -> None:
    settings = get_settings()
    client = get_qdrant()
    existing = {collection.name for collection in client.get_collections().collections}
    if settings.qdrant_collection in existing:
        collection = client.get_collection(settings.qdrant_collection)
        vector_config = collection.config.params.vectors
        size = vector_config.size if isinstance(vector_config, models.VectorParams) else None
        if size == settings.ollama_embedding_dimensions:
            return
        logger.warning(
            "Recreating Qdrant collection %s for embedding dimension %s (was %s)",
            settings.qdrant_collection,
            settings.ollama_embedding_dimensions,
            size,
        )
        client.delete_collection(settings.qdrant_collection)
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(
            size=settings.ollama_embedding_dimensions,
            distance=Distance.COSINE,
        ),
    )


def _filter(plan_ids: list[str] | None, organization_ids: list[str] | None) -> Filter | None:
    must: list[FieldCondition] = []
    if plan_ids:
        must.append(FieldCondition(key="plan_id", match=MatchAny(any=plan_ids)))
    if organization_ids:
        must.append(FieldCondition(key="organization_id", match=MatchAny(any=organization_ids)))
    return Filter(must=must) if must else None


def upsert_chunks(documents: list[Document], vectors: list[list[float]]) -> None:
    settings = get_settings()
    points: list[PointStruct] = []
    for document, vector in zip(documents, vectors, strict=True):
        point_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{document.metadata['document_id']}:{document.metadata['parent_id']}:{document.metadata['chunk_index']}",
        )
        payload = {**document.metadata, "text": document.page_content}
        points.append(PointStruct(id=str(point_id), vector=vector, payload=payload))
    if points:
        get_qdrant().upsert(collection_name=settings.qdrant_collection, points=points)


def delete_document_chunks(document_id: UUID | str) -> None:
    settings = get_settings()
    client = get_qdrant()
    existing = [collection.name for collection in client.get_collections().collections]
    if settings.qdrant_collection not in existing:
        return
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))]
            )
        ),
    )


def dense_search(
    query_vector: list[float],
    *,
    plan_ids: list[str] | None,
    organization_ids: list[str] | None,
    limit: int,
    score_threshold: float,
    with_vectors: bool = False,
) -> list[dict[str, Any]]:
    settings = get_settings()
    client = get_qdrant()
    existing = [collection.name for collection in client.get_collections().collections]
    if settings.qdrant_collection not in existing:
        return []
    query_filter = _filter(plan_ids, organization_ids)
    try:
        result = client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=with_vectors,
        )
        points = result.points
    except Exception:
        points = client.search(
            collection_name=settings.qdrant_collection,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=with_vectors,
        )

    records: list[dict[str, Any]] = []
    for point in points:
        payload = dict(point.payload or {})
        payload["_score"] = point.score
        payload["_vector"] = point.vector
        records.append(payload)
    return records


def scroll_all_payloads() -> list[dict[str, Any]]:
    settings = get_settings()
    client = get_qdrant()
    existing = [collection.name for collection in client.get_collections().collections]
    if settings.qdrant_collection not in existing:
        return []
    records: list[dict[str, Any]] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            records.append(dict(point.payload or {}))
        if offset is None:
            break
    return records
