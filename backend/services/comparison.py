import asyncio
from copy import deepcopy
from functools import partial
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.policies import SecurityContext, assert_comparison_access, can_view_pricing
from backend.domain.enums import ComparisonRequestStatus
from backend.domain.rules_engine.engine import PlanInput, run_comparison
from backend.models import ComparisonRequest, ComparisonResult, Employer, HealthcareProvider, Plan
from backend.schemas import (
    Citation,
    ComparisonRequestRead,
    ComparisonResultRead,
    EmployeeDemographics,
    EmployerRequirements,
    PlanEligibilityResult,
    PlanTerms,
    PricingTier,
)
from backend.services.narrative import generate_comparison_narrative
from backend.services.plan import active_plan_version


class ComparisonServiceError(Exception):
    pass


def redact_pricing_from_comparison(result_read: ComparisonResultRead) -> ComparisonResultRead:
    for row in result_read.eligibility_matrix:
        row.estimated_monthly_cost = None
        row.score_breakdown = {}
        row.total_score = None
        for rule in row.rules:
            if rule.rule_id == "budget_ceiling":
                rule.message = "Budget requirement evaluated"
                rule.details = {}

    result_read.audit_trace = deepcopy(result_read.audit_trace)
    for evaluation in result_read.audit_trace.get("plan_evaluations", []):
        evaluation["score_breakdown"] = {}
        for rule in evaluation.get("rules_evaluated", []):
            if rule.get("rule_id") == "budget_ceiling":
                rule["message"] = "Budget requirement evaluated"
                rule["details"] = {}
    return result_read


async def _get_employer_for_org(session: AsyncSession, organization_id: UUID) -> Employer:
    result = await session.execute(
        select(Employer).where(Employer.organization_id == organization_id)
    )
    employer = result.scalar_one_or_none()
    if employer is None:
        raise ComparisonServiceError("No employer profile found for this organization")
    return employer


async def _load_plans(session: AsyncSession, plan_ids: list[UUID]) -> list[Plan]:
    if not plan_ids:
        raise ComparisonServiceError("At least one plan_id is required")

    result = await session.execute(
        select(Plan)
        .where(Plan.id.in_(plan_ids))
        .options(
            selectinload(Plan.provider).selectinload(HealthcareProvider.hospitals),
            selectinload(Plan.versions),
        )
    )
    plans = list(result.scalars().all())

    if len(plans) != len(set(plan_ids)):
        found_ids = {p.id for p in plans}
        missing = [str(pid) for pid in plan_ids if pid not in found_ids]
        raise ComparisonServiceError(f"Plans not found: {', '.join(missing)}")

    return plans


def _to_plan_input(plan: Plan) -> PlanInput:
    hospital_count = len(plan.provider.hospitals) if plan.provider else 0
    version = active_plan_version(plan)
    terms = version.normalized_terms or version.raw_terms if version else plan.terms
    pricing_tiers = version.pricing_tiers if version else plan.pricing_tiers
    return PlanInput(
        plan_id=plan.id,
        plan_name=plan.name,
        provider_organization_id=plan.provider.organization_id,
        provider_name=plan.provider.name,
        coverage_type=version.coverage_type if version else plan.coverage_type,
        terms=PlanTerms.model_validate(terms),
        pricing_tiers=[PricingTier.model_validate(t) for t in pricing_tiers],
        network_hospital_count=hospital_count,
    )


def _build_comparison_read(
    request: ComparisonRequest,
    employer: Employer,
    result: ComparisonResult | None,
    ctx: SecurityContext,
) -> ComparisonRequestRead:
    result_read = None
    if result is not None:
        citations_raw = (result.audit_trace or {}).get("rag_citations") or []
        citations: list[Citation] = []
        for item in citations_raw:
            try:
                citations.append(Citation.model_validate(item))
            except Exception:
                continue
        result_read = ComparisonResultRead(
            id=result.id,
            comparison_request_id=result.comparison_request_id,
            eligibility_matrix=[
                PlanEligibilityResult.model_validate(row) for row in result.eligibility_matrix
            ],
            scored_ranking=[UUID(str(plan_id)) for plan_id in result.scored_ranking],
            narrative_explanation=result.narrative_explanation,
            citations=citations,
            audit_trace=result.audit_trace,
            created_at=result.created_at,
        )
        if not can_view_pricing(ctx):
            result_read = redact_pricing_from_comparison(result_read)

    return ComparisonRequestRead(
        id=request.id,
        employer_organization_id=employer.organization_id,
        plan_ids=[UUID(str(plan_id)) for plan_id in request.plan_ids],
        status=request.status,
        result=result_read,
        created_at=request.created_at,
    )


async def create_comparison(
    session: AsyncSession,
    ctx: SecurityContext,
    plan_ids: list[UUID],
) -> ComparisonRequestRead:
    employer = await _get_employer_for_org(session, ctx.organization_id)
    assert_comparison_access(ctx, employer.organization_id)

    plans = await _load_plans(session, plan_ids)

    demographics = EmployeeDemographics.model_validate(employer.demographics)
    requirements = EmployerRequirements.model_validate(employer.requirements)
    plan_inputs = [_to_plan_input(plan) for plan in plans]

    request = ComparisonRequest(
        employer_id=employer.id,
        plan_ids=[str(plan_id) for plan_id in plan_ids],
        status=ComparisonRequestStatus.PROCESSING,
    )
    session.add(request)
    await session.flush()

    try:
        eligibility_matrix, scored_ranking, audit_trace = run_comparison(
            plans=plan_inputs,
            demographics=demographics,
            requirements=requirements,
        )

        narrative, rag_citations = await asyncio.to_thread(
            partial(
                generate_comparison_narrative,
                plan_ids=plan_ids,
                eligibility_matrix=eligibility_matrix,
                requirements=requirements,
            )
        )
        audit_trace = {**audit_trace, "rag_citations": rag_citations}

        result = ComparisonResult(
            comparison_request_id=request.id,
            eligibility_matrix=[row.model_dump(mode="json") for row in eligibility_matrix],
            scored_ranking=[str(plan_id) for plan_id in scored_ranking],
            narrative_explanation=narrative,
            audit_trace=audit_trace,
        )
        session.add(result)
        request.status = ComparisonRequestStatus.COMPLETED
        await session.commit()
        await session.refresh(request)
        await session.refresh(result)
        return _build_comparison_read(request, employer, result, ctx)

    except Exception:
        request.status = ComparisonRequestStatus.FAILED
        await session.commit()
        raise


async def get_comparison(
    session: AsyncSession,
    ctx: SecurityContext,
    comparison_id: UUID,
) -> ComparisonRequestRead:
    result = await session.execute(
        select(ComparisonRequest)
        .where(ComparisonRequest.id == comparison_id)
        .options(
            selectinload(ComparisonRequest.employer),
            selectinload(ComparisonRequest.result),
        )
    )
    request = result.scalar_one_or_none()
    if request is None:
        raise ComparisonServiceError("Comparison not found")

    employer = request.employer
    assert_comparison_access(ctx, employer.organization_id)
    return _build_comparison_read(request, employer, request.result, ctx)
