from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.policies import (
    SecurityContext,
    can_view_provider_plans,
    can_view_provider_pricing,
    strip_pricing_from_plan,
)
from backend.domain.enums import PolicyReviewStatus
from backend.models import HealthcareProvider, Plan, PlanVersion
from backend.schemas import PlanRead, PlanTerms


class PlanServiceError(Exception):
    pass


def active_plan_version(plan: Plan, now: datetime | None = None) -> PlanVersion | None:
    now = now or datetime.now(UTC)
    candidates = [
        version
        for version in plan.versions
        if version.review_status == PolicyReviewStatus.APPROVED
        and (version.effective_from is None or version.effective_from <= now)
        and (version.effective_to is None or version.effective_to > now)
    ]
    return max(
        candidates,
        key=lambda version: version.effective_from or datetime.min.replace(tzinfo=UTC),
        default=None,
    )


def serialize_plan(plan: Plan, include_pricing: bool) -> PlanRead:
    plan_data = {
        "id": plan.id,
        "organization_id": plan.provider.organization_id,
        "provider_name": plan.provider.name,
        "name": plan.name,
        "coverage_type": plan.coverage_type,
        "terms": PlanTerms.model_validate(plan.terms),
        "pricing_tiers": plan.pricing_tiers if include_pricing else [],
        "network_hospital_count": len(plan.provider.hospitals),
        "source_document_id": plan.source_document_id,
    }

    if not include_pricing:
        plan_data = strip_pricing_from_plan(plan_data)
        plan_data["pricing_tiers"] = []

    return PlanRead.model_validate(plan_data)


async def list_visible_plans(session: AsyncSession, ctx: SecurityContext) -> list[PlanRead]:
    result = await session.execute(
        select(Plan).options(
            selectinload(Plan.provider).selectinload(HealthcareProvider.hospitals)
        )
    )
    plans = result.scalars().all()

    visible: list[PlanRead] = []
    for plan in plans:
        provider_org_id = plan.provider.organization_id
        if not can_view_provider_plans(ctx, provider_org_id):
            continue
        include_pricing = can_view_provider_pricing(ctx, provider_org_id)
        visible.append(serialize_plan(plan, include_pricing))
    return visible


async def get_visible_plan(
    session: AsyncSession,
    ctx: SecurityContext,
    plan_id: UUID,
) -> PlanRead:
    result = await session.execute(
        select(Plan)
        .where(Plan.id == plan_id)
        .options(selectinload(Plan.provider).selectinload(HealthcareProvider.hospitals))
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise PlanServiceError("Plan not found")

    provider_org_id = plan.provider.organization_id
    if not can_view_provider_plans(ctx, provider_org_id):
        raise PlanServiceError("Not authorized")

    include_pricing = can_view_provider_pricing(ctx, provider_org_id)
    return serialize_plan(plan, include_pricing)
