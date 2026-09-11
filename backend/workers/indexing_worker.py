from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.core.config import get_settings
from backend.db.session import async_session_factory
from backend.domain.enums import DocumentIndexStatus
from backend.models import Plan, PlanDocument
from backend.rag.indexing import index_plan_document
from backend.rag.retriever import rebuild_bm25_from_qdrant
from backend.rag.store import ensure_collection, get_qdrant, rag_configured
from backend.workers.indexing_queue import dequeue_document, enqueue_document

logger = logging.getLogger(__name__)


async def index_document_by_id(document_id: UUID) -> None:
    if not rag_configured():
        logger.warning("Skipping index job %s: RAG not configured", document_id)
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(PlanDocument)
            .where(PlanDocument.id == document_id)
            .options(selectinload(PlanDocument.plan).selectinload(Plan.provider))
        )
        document = result.scalar_one_or_none()
        if document is None:
            logger.warning("Index job %s: document not found", document_id)
            return
        if document.status == DocumentIndexStatus.INDEXED:
            return

        try:
            ensure_collection()
            await asyncio.to_thread(index_plan_document, document)
            document.status = DocumentIndexStatus.INDEXED
            if document.plan.source_document_id is None:
                document.plan.source_document_id = document.id
            await session.commit()
            await asyncio.to_thread(rebuild_bm25_from_qdrant)
            logger.info("Indexed document %s", document_id)
        except Exception:
            document.status = DocumentIndexStatus.FAILED
            await session.commit()
            logger.exception("Failed to index document %s", document_id)


async def enqueue_pending_documents() -> int:
    if not rag_configured():
        return 0
    ensure_collection()
    async with async_session_factory() as session:
        result = await session.execute(select(PlanDocument))
        documents = list(result.scalars().all())
        settings = get_settings()
        point_count = get_qdrant().count(
            collection_name=settings.qdrant_collection,
            exact=True,
        ).count
        if point_count == 0:
            for document in documents:
                if document.status == DocumentIndexStatus.INDEXED:
                    document.status = DocumentIndexStatus.PENDING
            await session.commit()
    enqueued = 0
    for document in documents:
        if document.status != DocumentIndexStatus.PENDING:
            continue
        if enqueue_document(document.id):
            enqueued += 1
    return enqueued


async def run_indexing_worker(stop_event: asyncio.Event) -> None:
    logger.info("Indexing worker started")
    while not stop_event.is_set():
        document_id = await asyncio.to_thread(dequeue_document, 2)
        if document_id is None:
            continue
        try:
            await index_document_by_id(document_id)
        except Exception:
            logger.exception("Unhandled index worker error for %s", document_id)
    logger.info("Indexing worker stopped")
