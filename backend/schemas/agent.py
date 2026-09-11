from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.rag import Citation


class AgentChatRequest(BaseModel):
    question: str = Field(min_length=1)
    plan_ids: list[UUID] = Field(default_factory=list)
    thread_id: str | None = Field(
        default=None,
        description="Optional conversation thread id for multi-turn memory",
    )


class AgentChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    route: str
    trace: list[dict[str, str]] = Field(default_factory=list)
    comparison_summary: dict | None = None
    thread_id: str | None = None
