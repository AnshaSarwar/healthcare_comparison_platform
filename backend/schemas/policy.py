from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.domain.enums import CoverageType, PolicyReviewStatus, UserRole
from backend.schemas.plan import PlanTerms, PricingTier


class PlanVersionCreateRequest(BaseModel):
    version_label: str = Field(min_length=1, max_length=128)
    coverage_type: CoverageType
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    raw_terms: dict = Field(default_factory=dict)
    normalized_terms: PlanTerms
    extraction_metadata: dict = Field(default_factory=dict)
    pricing_tiers: list[PricingTier] = Field(default_factory=list)
    source_document_id: UUID | None = None


class PlanVersionReviewRequest(BaseModel):
    review_status: PolicyReviewStatus
    review_notes: str | None = Field(default=None, max_length=2000)


class PlanVersionRead(BaseModel):
    id: UUID
    plan_id: UUID
    version_label: str
    coverage_type: CoverageType
    effective_from: datetime | None
    effective_to: datetime | None
    review_status: PolicyReviewStatus
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    review_notes: str | None
    raw_terms: dict
    normalized_terms: PlanTerms
    pricing_tiers: list[PricingTier]
    source_document_id: UUID | None
    imported_by_org_id: UUID | None
    imported_by_role: UserRole | None
    created_at: datetime

    model_config = {"from_attributes": True}
