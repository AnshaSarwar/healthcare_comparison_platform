from uuid import UUID

from pydantic import BaseModel, Field

from backend.domain.enums import CoverageType, OrganizationType, UserRole


class AgeBand(BaseModel):
    label: str
    min_age: int
    max_age: int
    count: int = Field(ge=0)


class EmployeeDemographics(BaseModel):
    age_bands: list[AgeBand] = Field(default_factory=list)
    department_breakdown: dict[str, int] = Field(default_factory=dict)
    total_dependents: int = Field(default=0, ge=0)
    role_tier_breakdown: dict[str, int] = Field(default_factory=dict)

    @property
    def headcount(self) -> int:
        return sum(band.count for band in self.age_bands)


class EmployerRequirements(BaseModel):
    budget_ceiling_per_employee: float = Field(gt=0)
    must_have_coverage_types: list[CoverageType] = Field(default_factory=list)
    min_headcount: int = Field(default=1, ge=1)
    avg_age: float | None = Field(default=None, ge=0)
    maternity_required: bool = False
    pre_existing_coverage_required: bool = False


class PricingTier(BaseModel):
    age_band_label: str
    monthly_premium_per_employee: float = Field(ge=0)


class PlanTerms(BaseModel):
    waiting_period_days: int = Field(default=0, ge=0)
    exclusions: list[str] = Field(default_factory=list)
    sub_limits: dict[str, float] = Field(default_factory=dict)
    maternity_coverage: bool = False
    maternity_waiting_days: int = Field(default=0, ge=0)
    pre_existing_condition_rules: str = ""
    min_employee_count: int = Field(default=1, ge=1)


class PlanRead(BaseModel):
    id: UUID
    organization_id: UUID
    provider_name: str
    name: str
    coverage_type: CoverageType
    terms: PlanTerms
    pricing_tiers: list[PricingTier]
    network_hospital_count: int = Field(default=0, ge=0)
    source_document_id: UUID | None = None

    model_config = {"from_attributes": True}


class PlanDetail(PlanRead):
    """Includes pricing — visible only to authorized roles."""


class EmployerRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    demographics: EmployeeDemographics
    requirements: EmployerRequirements

    model_config = {"from_attributes": True}


class OrganizationRead(BaseModel):
    id: UUID
    name: str
    org_type: OrganizationType

    model_config = {"from_attributes": True}


class UserRead(BaseModel):
    id: UUID
    email: str
    role: UserRole
    organization_id: UUID

    model_config = {"from_attributes": True}
