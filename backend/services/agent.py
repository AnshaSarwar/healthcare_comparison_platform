from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.agents.graph import get_benefits_agent
from backend.agents.thread_store import load_thread_messages, save_thread_messages
from backend.core.policies import SecurityContext, assert_comparison_access
from backend.domain.enums import UserRole
from backend.domain.rules_engine.engine import PlanInput, run_comparison
from backend.models import Employer, HealthcareProvider, Plan
from backend.observability.agent_trace import log_agent_event
from backend.rag.retriever import retrieve
from backend.rag.store import rag_configured
from backend.schemas import (
    Citation,
    EmployeeDemographics,
    EmployerRequirements,
    PlanTerms,
    PricingTier,
)
from backend.schemas.agent import AgentChatResponse
from backend.services.narrative import facts_block
from backend.services.plan import active_plan_version, list_visible_plans

logger = logging.getLogger(__name__)


class AgentServiceError(Exception):
    pass


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
        pricing_tiers=[PricingTier.model_validate(item) for item in pricing_tiers],
        network_hospital_count=hospital_count,
    )


def _build_compare_fn(
    plans: list[Plan],
    demographics: EmployeeDemographics,
    requirements: EmployerRequirements,
) -> Callable[[list[UUID]], tuple[str, dict[str, Any]]]:
    plan_by_id = {plan.id: plan for plan in plans}

    def compare_fn(plan_ids: list[UUID]) -> tuple[str, dict[str, Any]]:
        selected = [plan_by_id[plan_id] for plan_id in plan_ids if plan_id in plan_by_id]
        if not selected:
            raise AgentServiceError("No comparable plans in scope")
        inputs = [_to_plan_input(plan) for plan in selected]
        matrix, ranking, _audit = run_comparison(inputs, demographics, requirements)
        facts = facts_block(matrix, requirements)
        summary = {
            "ranking": [str(plan_id) for plan_id in ranking],
            "outcomes": [
                {
                    "plan_id": str(row.plan_id),
                    "plan_name": row.plan_name,
                    "overall_outcome": row.overall_outcome.value,
                    "total_score": row.total_score,
                }
                for row in matrix
            ],
        }
        return facts, summary

    return compare_fn


def _retrieve_fn(
    query: str,
    plan_ids: list[UUID] | None,
    organization_ids: list[UUID] | None,
) -> list[dict[str, Any]]:
    return retrieve(query, plan_ids=plan_ids, organization_ids=organization_ids)


async def resolve_agent_scope(
    session: AsyncSession,
    ctx: SecurityContext,
    requested_plan_ids: list[UUID],
) -> tuple[list[UUID], list[UUID] | None, Callable[[list[UUID]], tuple[str, dict[str, Any]]] | None]:
    visible = await list_visible_plans(session, ctx)
    allowed_ids = {plan.id for plan in visible}
    if requested_plan_ids:
        unknown = [plan_id for plan_id in requested_plan_ids if plan_id not in allowed_ids]
        if unknown:
            raise AgentServiceError("One or more plans are not visible to this user")
        plan_ids = list(requested_plan_ids)
    else:
        plan_ids = list(allowed_ids)

    organization_ids: list[UUID] | None = None
    if ctx.role == UserRole.HEALTHCARE_ORG_ADMIN:
        organization_ids = [ctx.organization_id]
        plan_ids = [
            plan.id
            for plan in visible
            if plan.id in set(plan_ids) and plan.organization_id == ctx.organization_id
        ]

    compare_fn = None
    if ctx.role in (UserRole.EMPLOYER_ADMIN, UserRole.PLATFORM_ADMIN):
        employer_result = await session.execute(
            select(Employer).where(Employer.organization_id == ctx.organization_id)
        )
        employer = employer_result.scalar_one_or_none()
        if employer is not None:
            try:
                assert_comparison_access(ctx, employer.organization_id)
            except Exception:
                employer = None
        if employer is not None and plan_ids:
            plans_result = await session.execute(
                select(Plan)
                .where(Plan.id.in_(plan_ids))
                .options(
                    selectinload(Plan.provider).selectinload(HealthcareProvider.hospitals),
                    selectinload(Plan.versions),
                )
            )
            plans = list(plans_result.scalars().all())
            demographics = EmployeeDemographics.model_validate(employer.demographics)
            requirements = EmployerRequirements.model_validate(employer.requirements)
            compare_fn = _build_compare_fn(plans, demographics, requirements)

    return plan_ids, organization_ids, compare_fn


def _to_response(state: dict[str, Any], thread_id: str) -> AgentChatResponse:
    citations = [Citation.model_validate(item) for item in state.get("citations") or []]
    return AgentChatResponse(
        answer=state.get("answer") or "",
        citations=citations,
        route=str(state.get("route") or "policy_qa"),
        trace=list(state.get("trace") or []),
        comparison_summary=state.get("comparison_summary"),
        thread_id=thread_id,
    )


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def stream_agent_chat(
    session: AsyncSession,
    ctx: SecurityContext,
    question: str,
    requested_plan_ids: list[UUID],
    thread_id: str | None = None,
) -> AsyncIterator[str]:
    if not rag_configured():
        raise AgentServiceError("RAG is not configured")

    plan_ids, organization_ids, compare_fn = await resolve_agent_scope(
        session, ctx, requested_plan_ids
    )
    if not plan_ids:
        raise AgentServiceError("No visible plans available for this user")

    resolved_thread = thread_id or str(uuid.uuid4())
    prior_messages = load_thread_messages(resolved_thread, str(ctx.organization_id))
    initial = {
        "question": question,
        "plan_ids": [str(plan_id) for plan_id in plan_ids],
        "organization_ids": [str(item) for item in organization_ids]
        if organization_ids is not None
        else None,
        "max_retries": 1,
        "retry_count": 0,
        "trace": [],
        "messages": prior_messages,
        "records": [],
    }
    # Do not put thread_id in LangGraph config — the compiled graph has no checkpointer.
    # Multi-turn memory is Redis (thread_store), not graph checkpoints.
    config = {
        "configurable": {
            "retrieve_fn": _retrieve_fn,
            "compare_fn": compare_fn,
        }
    }
    graph = get_benefits_agent()
    log_agent_event(
        "chat_start",
        "invoke",
        thread_id=resolved_thread,
        user_id=str(ctx.user_id),
        role=ctx.role.value,
        plan_count=len(plan_ids),
    )

    previous_trace_len = 0
    final_state: dict[str, Any] = dict(initial)
    try:
        async for mode, chunk in graph.astream(
            initial,
            config=config,
            stream_mode=["updates", "custom"],
        ):
            if mode == "custom":
                if isinstance(chunk, dict) and chunk.get("type") == "token":
                    yield _sse(chunk)
                continue

            if mode != "updates" or not isinstance(chunk, dict):
                continue

            for _node_name, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                final_state.update(update)
                trace = list(update.get("trace") or [])
                if len(trace) > previous_trace_len:
                    for item in trace[previous_trace_len:]:
                        yield _sse({"type": "step", **item})
                    previous_trace_len = len(trace)
    except Exception as exc:
        logger.exception("Agent graph failed")
        yield _sse({"type": "error", "detail": str(exc)})
        return

    if not (final_state.get("answer") or final_state.get("trace")):
        yield _sse({"type": "error", "detail": "Agent produced no result"})
        return

    response = _to_response(final_state, resolved_thread)
    save_thread_messages(
        resolved_thread,
        str(ctx.organization_id),
        list(final_state.get("messages") or []),
    )
    log_agent_event(
        "chat_end",
        "complete",
        thread_id=resolved_thread,
        route=response.route,
        citation_count=len(response.citations),
    )
    yield _sse({"type": "final", **response.model_dump(mode="json")})
