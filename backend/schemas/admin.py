from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from backend.domain.enums import CoverageType, OrganizationType, UserRole
from backend.schemas.plan import (
    EmployeeDemographics,
    EmployerRequirements,
    PlanTerms,
    PricingTier,
)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    organization_name: str = Field(min_length=1, max_length=255)
    org_type: OrganizationType
    profile_name: str = Field(min_length=1, max_length=255)


class MeResponse(BaseModel):
    id: UUID
    email: str
    role: UserRole
    organization_id: UUID
    organization_name: str
    org_type: OrganizationType


class EmployerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    demographics: EmployeeDemographics | None = None
    requirements: EmployerRequirements | None = None


class PlanCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    coverage_type: CoverageType
    terms: PlanTerms
    pricing_tiers: list[PricingTier] = Field(default_factory=list)


class PlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    coverage_type: CoverageType | None = None
    terms: PlanTerms | None = None
    pricing_tiers: list[PricingTier] | None = None


class HospitalCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=128)
    tier: str = Field(default="standard", max_length=64)


class HospitalRead(BaseModel):
    id: UUID
    provider_id: UUID
    name: str
    city: str
    tier: str

    model_config = {"from_attributes": True}


class ProviderRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    hospital_count: int = 0

    model_config = {"from_attributes": True}


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    org_type: OrganizationType
    profile_name: str = Field(min_length=1, max_length=255)


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole
    organization_id: UUID
