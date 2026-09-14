from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.domain.enums import DocumentIndexStatus
from backend.models import Plan, PlanDocument
from backend.rag.embeddings import get_embeddings
from backend.rag.loaders import load_pages, load_text, read_path
from backend.rag.retriever import rebuild_bm25_from_qdrant
from backend.rag.splitters import split_for_parent_child
from backend.rag.store import delete_document_chunks, ensure_collection, rag_configured, upsert_chunks

logger = logging.getLogger(__name__)

SEED_FILES = {
    "HealthFirst Corporate OPD+IPD": "data/plans/healthfirst_corporate_opd_ipd.md",
    "MediCare Essential IPD": "data/plans/medicare_essential_ipd.md",
    "MediCare Premium OPD+IPD": "data/plans/medicare_premium_opd_ipd.md",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def index_plan_document(document: PlanDocument, text: str | None = None) -> None:
    plan = document.plan
    provider = plan.provider
    if text is None:
        path = Path(document.storage_path)
        pages = load_pages(path.name, path.read_bytes())
    else:
        # Caller already loaded/joined the text (e.g. re-indexing from a cached
        # string) — no page boundaries are available for this path.
        pages = [(None, text)]
    base_meta = {
        "document_id": str(document.id),
        "plan_id": str(plan.id),
        "organization_id": str(provider.organization_id),
        "plan_name": plan.name,
    }
    chunks: list = []
    for page_number, page_text in pages:
        chunks.extend(
            split_for_parent_child(page_text, {**base_meta, "page_number": page_number})
        )
    if not chunks:
        raise ValueError("No chunks produced from document")
    vectors = get_embeddings().embed_documents([chunk.page_content for chunk in chunks])
    delete_document_chunks(document.id)
    upsert_chunks(chunks, vectors)


async def seed_plan_documents(session: AsyncSession) -> None:
    result = await session.execute(
        select(Plan).options(selectinload(Plan.documents), selectinload(Plan.provider))
    )
    plans = list(result.scalars().all())
    root = repo_root()
    created = False
    for plan in plans:
        relative = SEED_FILES.get(plan.name)
        if relative is None or plan.documents:
            continue
        path = root / relative
        if not path.exists():
            logger.warning("Seed booklet missing: %s", path)
            continue
        text = read_path(path)
        document = PlanDocument(
            plan_id=plan.id,
            filename=path.name,
            storage_path=str(path.resolve()),
            content_hash=content_hash(text),
            status=DocumentIndexStatus.PENDING,
        )
        session.add(document)
        await session.flush()
        plan.source_document_id = document.id
        created = True
    if created:
        await session.commit()
    else:
        await session.flush()


async def index_pending_documents(session: AsyncSession) -> None:
    if not rag_configured():
        logger.warning("OPENAI_API_KEY is empty; skipping RAG indexing")
        rebuild_bm25_from_qdrant()
        return

    try:
        ensure_collection()
    except Exception as exc:
        logger.warning("Qdrant unavailable; skipping RAG indexing: %s", exc)
        return

    result = await session.execute(
        select(PlanDocument).options(
            selectinload(PlanDocument.plan).selectinload(Plan.provider)
        )
    )
    documents = list(result.scalars().all())
    changed = False
    for document in documents:
        if document.status == DocumentIndexStatus.INDEXED:
            continue
        try:
            index_plan_document(document)
            document.status = DocumentIndexStatus.INDEXED
            if document.plan.source_document_id is None:
                document.plan.source_document_id = document.id
            changed = True
        except Exception:
            document.status = DocumentIndexStatus.FAILED
            changed = True
            logger.exception("Failed to index document %s", document.id)
    if changed:
        await session.commit()
    rebuild_bm25_from_qdrant()


def save_upload(document_id: UUID, filename: str, content: bytes) -> Path:
    directory = repo_root() / "data" / "uploads" / str(document_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(content)
    return path
