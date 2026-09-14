import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.domain.enums import (
    ComparisonRequestStatus,
    CoverageType,
    DocumentIndexStatus,
    OrganizationType,
    PolicyReviewStatus,
    UserRole,
)
from backend.models.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    org_type: Mapped[OrganizationType] = mapped_column(Enum(OrganizationType), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    employer: Mapped["Employer | None"] = relationship(back_populates="organization", uselist=False)
    healthcare_provider: Mapped["HealthcareProvider | None"] = relationship(
        back_populates="organization", uselist=False
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="users")


class Employer(Base):
    __tablename__ = "employers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    demographics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    requirements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="employer")
    comparison_requests: Mapped[list["ComparisonRequest"]] = relationship(back_populates="employer")


class HealthcareProvider(Base):
    __tablename__ = "healthcare_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="healthcare_provider")
    plans: Mapped[list["Plan"]] = relationship(back_populates="provider")
    hospitals: Mapped[list["Hospital"]] = relationship(back_populates="provider")


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healthcare_providers.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(64), default="standard")

    provider: Mapped["HealthcareProvider"] = relationship(back_populates="hospitals")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("healthcare_providers.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    coverage_type: Mapped[CoverageType] = mapped_column(Enum(CoverageType), nullable=False)
    terms: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    pricing_tiers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_documents.id", use_alter=True, name="fk_plans_source_document_id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    provider: Mapped["HealthcareProvider"] = relationship(back_populates="plans")
    documents: Mapped[list["PlanDocument"]] = relationship(
        back_populates="plan",
        foreign_keys="PlanDocument.plan_id",
    )
    versions: Mapped[list["PlanVersion"]] = relationship(back_populates="plan")


class PlanDocument(Base):
    __tablename__ = "plan_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentIndexStatus] = mapped_column(
        Enum(DocumentIndexStatus), default=DocumentIndexStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plan: Mapped["Plan"] = relationship(back_populates="documents", foreign_keys=[plan_id])


class PlanVersion(Base):
    __tablename__ = "plan_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False
    )
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    coverage_type: Mapped[CoverageType] = mapped_column(Enum(CoverageType), nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_status: Mapped[PolicyReviewStatus] = mapped_column(
        Enum(PolicyReviewStatus), nullable=False, default=PolicyReviewStatus.DRAFT
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_terms: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    normalized_terms: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    extraction_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    pricing_tiers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plan_documents.id"), nullable=True
    )
    imported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    imported_by_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    imported_by_role: Mapped[UserRole | None] = mapped_column(Enum(UserRole), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plan: Mapped["Plan"] = relationship(back_populates="versions")
    source_document: Mapped["PlanDocument | None"] = relationship(
        foreign_keys=[source_document_id]
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id"), nullable=True
    )


class ComparisonRequest(Base):
    __tablename__ = "comparison_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employers.id"), nullable=False
    )
    plan_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[ComparisonRequestStatus] = mapped_column(
        Enum(ComparisonRequestStatus), default=ComparisonRequestStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employer: Mapped["Employer"] = relationship(back_populates="comparison_requests")
    result: Mapped["ComparisonResult | None"] = relationship(
        back_populates="comparison_request", uselist=False
    )


class ComparisonResult(Base):
    __tablename__ = "comparison_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comparison_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comparison_requests.id"), unique=True, nullable=False
    )
    eligibility_matrix: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    scored_ranking: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    narrative_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_trace: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    comparison_request: Mapped["ComparisonRequest"] = relationship(back_populates="result")
