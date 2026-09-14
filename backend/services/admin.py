from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.policies import (
    AccessDeniedError,
    SecurityContext,
    can_manage_employer,
    can_manage_provider,
    can_view_provider_plans,
    is_platform_admin,
)
from backend.core.security import hash_password
from backend.domain.enums import OrganizationType, PolicyReviewStatus, UserRole
from backend.models import (
    Employer,
    HealthcareProvider,
    Hospital,
    Organization,
    Plan,
    PlanVersion,
    User,
)
from backend.schemas.admin import (
    EmployerUpdateRequest,
    HospitalCreateRequest,
    MeResponse,
    OrganizationCreateRequest,
    PlanCreateRequest,
    PlanUpdateRequest,
    RegisterRequest,
    UserCreateRequest,
)
from backend.schemas.policy import PlanVersionCreateRequest, PlanVersionReviewRequest
from backend.services.plan import serialize_plan


class AdminServiceError(Exception):
    pass


async def get_me(session: AsyncSession, ctx: SecurityContext) -> MeResponse:
    result = await session.execute(
        select(User).options(selectinload(User.organization)).where(User.id == ctx.user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise AdminServiceError("User not found")
    return MeResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        organization_id=user.organization_id,
        organization_name=user.organization.name,
        org_type=user.organization.org_type,
    )


async def register_tenant(session: AsyncSession, body: RegisterRequest) -> User:
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise AdminServiceError("Email already registered")

    if body.org_type == OrganizationType.EMPLOYER:
        role = UserRole.EMPLOYER_ADMIN
    elif body.org_type == OrganizationType.HEALTHCARE_PROVIDER:
        role = UserRole.HEALTHCARE_ORG_ADMIN
    else:
        raise AdminServiceError("Unsupported organization type for self-registration")

    org = Organization(id=uuid4(), name=body.organization_name, org_type=body.org_type)
    session.add(org)
    await session.flush()

    if body.org_type == OrganizationType.EMPLOYER:
        session.add(
            Employer(
                id=uuid4(),
                organization_id=org.id,
                name=body.profile_name,
                demographics={"age_bands": [], "department_breakdown": {}, "total_dependents": 0},
                requirements={
                    "budget_ceiling_per_employee": 500,
                    "must_have_coverage_types": ["opd_ipd"],
                    "min_headcount": 1,
                    "maternity_required": False,
                    "pre_existing_coverage_required": False,
                },
            )
        )
    else:
        session.add(
            HealthcareProvider(id=uuid4(), organization_id=org.id, name=body.profile_name)
        )

    user = User(
        id=uuid4(),
        email=body.email,
        hashed_password=hash_password(body.password),
        role=role,
        organization_id=org.id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_employer_me(session: AsyncSession, ctx: SecurityContext) -> Employer:
    result = await session.execute(
        select(Employer).where(Employer.organization_id == ctx.organization_id)
    )
    employer = result.scalar_one_or_none()
    if employer is None:
        raise AdminServiceError("Employer profile not found")
    if not can_manage_employer(ctx, employer.organization_id):
        raise AccessDeniedError("Not authorized to access this employer")
    return employer


async def update_employer_me(
    session: AsyncSession, ctx: SecurityContext, body: EmployerUpdateRequest
) -> Employer:
    employer = await get_employer_me(session, ctx)
    if body.name is not None:
        employer.name = body.name
    if body.demographics is not None:
        employer.demographics = body.demographics.model_dump()
    if body.requirements is not None:
        employer.requirements = body.requirements.model_dump(mode="json")
    await session.commit()
    await session.refresh(employer)
    return employer


async def get_provider_me(session: AsyncSession, ctx: SecurityContext) -> HealthcareProvider:
    result = await session.execute(
        select(HealthcareProvider)
        .options(selectinload(HealthcareProvider.hospitals))
        .where(HealthcareProvider.organization_id == ctx.organization_id)
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise AdminServiceError("Provider profile not found")
    if not can_manage_provider(ctx, provider.organization_id):
        raise AccessDeniedError("Not authorized to access this provider")
    return provider


async def add_hospital(
    session: AsyncSession, ctx: SecurityContext, body: HospitalCreateRequest
) -> Hospital:
    provider = await get_provider_me(session, ctx)
    hospital = Hospital(
        id=uuid4(),
        provider_id=provider.id,
        name=body.name,
        city=body.city,
        tier=body.tier,
    )
    session.add(hospital)
    await session.commit()
    await session.refresh(hospital)
    return hospital


async def create_plan(
    session: AsyncSession, ctx: SecurityContext, body: PlanCreateRequest
):
    provider = await get_provider_me(session, ctx)
    plan = Plan(
        id=uuid4(),
        provider_id=provider.id,
        name=body.name,
        coverage_type=body.coverage_type,
        terms=body.terms.model_dump(),
        pricing_tiers=[tier.model_dump() for tier in body.pricing_tiers],
    )
    session.add(plan)
    await session.commit()
    result = await session.execute(
        select(Plan)
        .where(Plan.id == plan.id)
        .options(selectinload(Plan.provider).selectinload(HealthcareProvider.hospitals))
    )
    loaded = result.scalar_one()
    return serialize_plan(loaded, include_pricing=True)


async def update_plan(
    session: AsyncSession, ctx: SecurityContext, plan_id: UUID, body: PlanUpdateRequest
):
    result = await session.execute(
        select(Plan)
        .options(selectinload(Plan.provider).selectinload(HealthcareProvider.hospitals))
        .where(Plan.id == plan_id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise AdminServiceError("Plan not found")
    if not can_manage_provider(ctx, plan.provider.organization_id):
        raise AccessDeniedError("Not authorized to manage this plan")
    if body.name is not None:
        plan.name = body.name
    if body.coverage_type is not None:
        plan.coverage_type = body.coverage_type
    if body.terms is not None:
        plan.terms = body.terms.model_dump()
    if body.pricing_tiers is not None:
        plan.pricing_tiers = [tier.model_dump() for tier in body.pricing_tiers]
    await session.commit()
    await session.refresh(plan)
    result = await session.execute(
        select(Plan)
        .where(Plan.id == plan.id)
        .options(selectinload(Plan.provider).selectinload(HealthcareProvider.hospitals))
    )
    loaded = result.scalar_one()
    return serialize_plan(loaded, include_pricing=True)


async def _get_plan_for_version(session: AsyncSession, plan_id: UUID) -> Plan:
    result = await session.execute(
        select(Plan)
        .where(Plan.id == plan_id)
        .options(selectinload(Plan.provider))
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise AdminServiceError("Plan not found")
    return plan


async def create_plan_version(
    session: AsyncSession,
    ctx: SecurityContext,
    plan_id: UUID,
    body: PlanVersionCreateRequest,
) -> PlanVersion:
    plan = await _get_plan_for_version(session, plan_id)
    if not can_manage_provider(ctx, plan.provider.organization_id):
        raise AccessDeniedError("Not authorized to create a plan version")
    if body.effective_to is not None and body.effective_from is not None and body.effective_to <= body.effective_from:
        raise AdminServiceError("effective_to must be after effective_from")
    version = PlanVersion(
        plan_id=plan.id,
        version_label=body.version_label,
        coverage_type=body.coverage_type,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        review_status=PolicyReviewStatus.NEEDS_REVIEW,
        raw_terms=body.raw_terms,
        normalized_terms=body.normalized_terms.model_dump(),
        extraction_metadata={},
        pricing_tiers=[tier.model_dump() for tier in body.pricing_tiers],
        source_document_id=body.source_document_id,
        imported_by_user_id=ctx.user_id,
        imported_by_org_id=ctx.organization_id,
        imported_by_role=ctx.role,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version


async def list_plan_versions(
    session: AsyncSession, ctx: SecurityContext, plan_id: UUID
) -> list[PlanVersion]:
    plan = await _get_plan_for_version(session, plan_id)
    if not can_view_provider_plans(ctx, plan.provider.organization_id):
        raise AccessDeniedError("Not authorized to view plan versions")
    result = await session.execute(
        select(PlanVersion)
        .where(PlanVersion.plan_id == plan.id)
        .order_by(PlanVersion.effective_from.desc().nullslast(), PlanVersion.created_at.desc())
    )
    return list(result.scalars().all())


async def review_plan_version(
    session: AsyncSession,
    ctx: SecurityContext,
    version_id: UUID,
    body: PlanVersionReviewRequest,
) -> PlanVersion:
    result = await session.execute(
        select(PlanVersion).options(selectinload(PlanVersion.plan).selectinload(Plan.provider)).where(
            PlanVersion.id == version_id
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise AdminServiceError("Plan version not found")
    provider_org_id = version.plan.provider.organization_id
    if not can_manage_provider(ctx, provider_org_id):
        raise AccessDeniedError("Not authorized to review this plan version")
    if body.review_status in (PolicyReviewStatus.REJECTED, PolicyReviewStatus.NEEDS_CORRECTION) and not body.review_notes:
        raise AdminServiceError("Review notes are required for rejection or correction")
    if body.review_status == PolicyReviewStatus.APPROVED:
        evidence = (version.extraction_metadata or {}).get("evidence") or []
        required_fields = {
            "coverage_type",
            "waiting_period_days",
            "maternity_coverage",
            "maternity_waiting_days",
            "pre_existing_condition_rules",
            "min_employee_count",
        }
        evidence_fields = {item.get("field") for item in evidence if isinstance(item, dict)}
        if not required_fields.issubset(evidence_fields):
            raise AdminServiceError("Cannot approve: required extraction evidence is missing")
        if any(float(item.get("confidence", 0)) < 0.7 for item in evidence if isinstance(item, dict)):
            raise AdminServiceError("Cannot approve: extraction confidence is too low")
        await session.execute(
            PlanVersion.__table__.update()
            .where(PlanVersion.plan_id == version.plan_id)
            .where(PlanVersion.id != version.id)
            .where(PlanVersion.review_status == PolicyReviewStatus.APPROVED)
            .values(review_status=PolicyReviewStatus.ARCHIVED)
        )
    version.review_status = body.review_status
    version.reviewed_by = ctx.user_id
    version.reviewed_at = datetime.now(UTC)
    version.review_notes = body.review_notes
    await session.commit()
    await session.refresh(version)
    return version


async def list_organizations(session: AsyncSession, ctx: SecurityContext) -> list[Organization]:
    if not is_platform_admin(ctx):
        raise AccessDeniedError("Platform admin only")
    result = await session.execute(select(Organization).order_by(Organization.name))
    return list(result.scalars().all())


async def create_organization(
    session: AsyncSession, ctx: SecurityContext, body: OrganizationCreateRequest
) -> Organization:
    if not is_platform_admin(ctx):
        raise AccessDeniedError("Platform admin only")
    org = Organization(id=uuid4(), name=body.name, org_type=body.org_type)
    session.add(org)
    await session.flush()
    if body.org_type == OrganizationType.EMPLOYER:
        session.add(
            Employer(
                id=uuid4(),
                organization_id=org.id,
                name=body.profile_name,
                demographics={"age_bands": [], "department_breakdown": {}, "total_dependents": 0},
                requirements={
                    "budget_ceiling_per_employee": 500,
                    "must_have_coverage_types": ["opd_ipd"],
                    "min_headcount": 1,
                    "maternity_required": False,
                    "pre_existing_coverage_required": False,
                },
            )
        )
    else:
        session.add(
            HealthcareProvider(id=uuid4(), organization_id=org.id, name=body.profile_name)
        )
    await session.commit()
    await session.refresh(org)
    return org


async def create_user(session: AsyncSession, ctx: SecurityContext, body: UserCreateRequest) -> User:
    if not is_platform_admin(ctx):
        raise AccessDeniedError("Platform admin only")
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise AdminServiceError("Email already registered")
    org = await session.get(Organization, body.organization_id)
    if org is None:
        raise AdminServiceError("Organization not found")
    if body.role == UserRole.EMPLOYER_ADMIN and org.org_type != OrganizationType.EMPLOYER:
        raise AdminServiceError("employer_admin requires an employer organization")
    if (
        body.role == UserRole.HEALTHCARE_ORG_ADMIN
        and org.org_type != OrganizationType.HEALTHCARE_PROVIDER
    ):
        raise AdminServiceError("healthcare_org_admin requires a provider organization")
    user = User(
        id=uuid4(),
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role,
        organization_id=org.id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
