from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.domain.enums import DocumentIndexStatus


class Citation(BaseModel):
    plan_id: UUID
    plan_name: str
    section: str
    quote: str
    document_id: UUID
    page_number: int | None = None


class SourceChunk(BaseModel):
    """Shape of one entry in the metadata-first `"sources"` SSE event.

    Not validated at runtime today (SSE payloads bypass FastAPI response models
    entirely) — this exists for documentation/typing and for tests that want to assert
    against a concrete shape.
    """

    index: int
    plan_id: UUID | None = None
    plan_name: str | None = None
    section: str | None = None
    document_id: UUID | None = None
    chunk_index: int | None = None
    page_number: int | None = None
    score: float | None = None


class PlanDocumentRead(BaseModel):
    id: UUID
    plan_id: UUID
    filename: str
    status: DocumentIndexStatus
    content_hash: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RagQueryRequest(BaseModel):
    question: str = Field(min_length=1)
    plan_ids: list[UUID] = Field(default_factory=list)


class RagQueryResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    cached: bool = False
