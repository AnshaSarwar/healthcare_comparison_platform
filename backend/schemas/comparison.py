from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.domain.enums import ComparisonRequestStatus, EligibilityOutcome
from backend.schemas.rag import Citation


class EligibilityRuleResult(BaseModel):
    rule_id: str
    rule_name: str
    outcome: EligibilityOutcome
    message: str
    details: dict = Field(default_factory=dict)


class PlanEligibilityResult(BaseModel):
    plan_id: UUID
    plan_name: str
    provider_organization_id: UUID
    provider_name: str = ""
    overall_outcome: EligibilityOutcome
    rules: list[EligibilityRuleResult]
    estimated_monthly_cost: float | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    total_score: float | None = 0.0


class ComparisonResultRead(BaseModel):
    id: UUID
    comparison_request_id: UUID
    eligibility_matrix: list[PlanEligibilityResult]
    scored_ranking: list[UUID]
    narrative_explanation: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    audit_trace: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class ComparisonRequestRead(BaseModel):
    id: UUID
    employer_organization_id: UUID
    plan_ids: list[UUID]
    status: ComparisonRequestStatus
    result: ComparisonResultRead | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ComparisonCreateRequest(BaseModel):
    plan_ids: list[UUID] = Field(min_length=1)
