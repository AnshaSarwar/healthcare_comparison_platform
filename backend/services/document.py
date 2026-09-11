from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.policies import SecurityContext, can_manage_plan_documents, can_view_provider_plans
from backend.domain.enums import DocumentIndexStatus, PolicyReviewStatus
from backend.models import Plan, PlanDocument, PlanVersion
from backend.policy_extraction import extract_policy_terms
from backend.rag.indexing import content_hash, save_upload
from backend.rag.loaders import load_text
from backend.rag.store import rag_configured
from backend.schemas import PlanDocumentRead
from backend.workers.indexing_queue import enqueue_document

logger = logging.getLogger(__name__)

ALLOWED_SUFFIXES = {".md", ".txt", ".pdf"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class DocumentServiceError(Exception):
    pass


def _to_read(document: PlanDocument) -> PlanDocumentRead:
    return PlanDocumentRead.model_validate(document)


async def get_document_file(
    session: AsyncSession,
    ctx: SecurityContext,
    document_id: UUID,
) -> tuple[Path, str]:
    result = await session.execute(
        select(PlanDocument)
        .where(PlanDocument.id == document_id)
        .options(selectinload(PlanDocument.plan).selectinload(Plan.provider))
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise DocumentServiceError("Document not found")
    org_id = document.plan.provider.organization_id
    if not can_view_provider_plans(ctx, org_id):
        raise DocumentServiceError("Not authorized")
    path = Path(document.storage_path).resolve()
    if not path.is_file():
        raise DocumentServiceError("Document file not found")
    return path, document.filename


async def _load_plan(session: AsyncSession, plan_id: UUID) -> Plan:
    result = await session.execute(
        select(Plan)
        .where(Plan.id == plan_id)
        .options(selectinload(Plan.provider), selectinload(Plan.documents))
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise DocumentServiceError("Plan not found")
    return plan


async def get_document(
    session: AsyncSession,
    ctx: SecurityContext,
    document_id: UUID,
) -> PlanDocumentRead:
    result = await session.execute(
        select(PlanDocument)
        .where(PlanDocument.id == document_id)
        .options(selectinload(PlanDocument.plan).selectinload(Plan.provider))
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise DocumentServiceError("Document not found")
    org_id = document.plan.provider.organization_id
    if not can_view_provider_plans(ctx, org_id):
        raise DocumentServiceError("Not authorized")
    return _to_read(document)


async def upload_and_index(
    session: AsyncSession,
    ctx: SecurityContext,
    plan_id: UUID,
    filename: str,
    content: bytes,
) -> PlanDocumentRead:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise DocumentServiceError("Only .md, .txt, and .pdf files are accepted")
    if len(content) > MAX_UPLOAD_BYTES:
        raise DocumentServiceError("File is too large")

    plan = await _load_plan(session, plan_id)
    org_id = plan.provider.organization_id
    if not can_manage_plan_documents(ctx, org_id):
        raise DocumentServiceError("Not authorized")
    if not rag_configured():
        raise DocumentServiceError("RAG is not configured")

    text = load_text(filename, content)
    digest = content_hash(text)
    extracted = extract_policy_terms(text)
    document = PlanDocument(
        plan_id=plan.id,
        filename=filename,
        storage_path="",
        content_hash=digest,
        status=DocumentIndexStatus.PENDING,
    )
    session.add(document)
    await session.flush()

    version = PlanVersion(
        plan_id=plan.id,
        version_label=f"Imported {filename}",
        coverage_type=extracted.coverage_type,
        review_status=PolicyReviewStatus.NEEDS_REVIEW,
        raw_terms={
            "source_filename": filename,
            "extraction_status": "pending",
        },
        normalized_terms=extracted.terms.model_dump(),
        extraction_metadata=extracted.metadata,
        pricing_tiers=plan.pricing_tiers,
        source_document_id=document.id,
        imported_by_user_id=ctx.user_id,
        imported_by_org_id=ctx.organization_id,
        imported_by_role=ctx.role,
    )
    session.add(version)

    path = save_upload(document.id, filename, content)
    document.storage_path = str(path)
    plan.source_document_id = document.id

    if not enqueue_document(document.id):
        raise DocumentServiceError("Indexing queue unavailable (is Redis running?)")

    await session.commit()
    await session.refresh(document)
    logger.info("Queued document %s for async indexing", document.id)
    return _to_read(document)
