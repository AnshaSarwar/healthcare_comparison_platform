from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_security_context
from backend.core.policies import SecurityContext
from backend.schemas import PlanDocumentRead
from fastapi.responses import FileResponse

from backend.services.document import (
    DocumentServiceError,
    get_document,
    get_document_file,
    upload_and_index,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=PlanDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    plan_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> PlanDocumentRead:
    content = await file.read()
    filename = file.filename or "upload.md"
    try:
        return await upload_and_index(db, ctx, plan_id, filename, content)
    except DocumentServiceError as exc:
        message = str(exc)
        if message == "Plan not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
        if message == "Not authorized":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message) from exc
        if message == "RAG is not configured":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc


@router.get("/{document_id}", response_model=PlanDocumentRead)
async def fetch_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> PlanDocumentRead:
    try:
        return await get_document(db, ctx, document_id)
    except DocumentServiceError as exc:
        message = str(exc)
        if message == "Document not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message) from exc


@router.get("/{document_id}/content")
async def fetch_document_content(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> FileResponse:
    try:
        path, filename = await get_document_file(db, ctx, document_id)
    except DocumentServiceError as exc:
        message = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=code, detail=message) from exc
    return FileResponse(path, filename=filename)
