from __future__ import annotations

import logging
from uuid import UUID

from backend.rag.generate import citations_from_answer, generate_answer
from backend.rag.retriever import retrieve
from backend.rag.store import rag_configured
from backend.schemas import EmployerRequirements, PlanEligibilityResult

logger = logging.getLogger(__name__)


def facts_block(
    eligibility_matrix: list[PlanEligibilityResult],
    requirements: EmployerRequirements,
) -> str:
    coverage = ", ".join(item.value for item in requirements.must_have_coverage_types) or "unspecified"
    lines = [
        "COMPARISON FACTS (rules engine, not policy wording):",
        f"- Required coverage: {coverage}",
        f"- Maternity required: {requirements.maternity_required}",
        f"- Pre-existing coverage required: {requirements.pre_existing_coverage_required}",
        f"- Minimum headcount: {requirements.min_headcount}",
    ]
    for row in eligibility_matrix:
        lines.append(
            f"- {row.plan_name}: outcome={row.overall_outcome.value}, score={row.total_score:.4f}"
        )
        for rule in row.rules:
            if rule.outcome.value != "pass":
                if rule.rule_id == "budget_ceiling":
                    lines.append(f"  - {rule.rule_name}: {rule.outcome.value}")
                else:
                    lines.append(f"  - {rule.rule_name}: {rule.outcome.value} ({rule.message})")
    return "\n".join(lines)


# Backwards-compatible alias used by older call sites / notes.
_facts_block = facts_block


def _narrative_question(requirements: EmployerRequirements) -> str:
    coverage = ", ".join(item.value for item in requirements.must_have_coverage_types) or "group medical"
    return (
        "Write a concise comparison of these group health plans for an employer buyer. "
        f"They require coverage types [{coverage}], "
        f"maternity={requirements.maternity_required}, "
        f"pre-existing condition cover={requirements.pre_existing_coverage_required}. "
        "Explain waiting periods, exclusions, maternity, and pre-existing condition rules "
        "using only the retrieved policy wording. Cite sources with [n]."
    )


def generate_comparison_narrative(
    *,
    plan_ids: list[UUID],
    eligibility_matrix: list[PlanEligibilityResult],
    requirements: EmployerRequirements,
) -> tuple[str | None, list[dict]]:
    if not rag_configured():
        return None, []
    try:
        question = _narrative_question(requirements)
        records = retrieve(question, plan_ids=plan_ids)
        if not records:
            return None, []
        facts = _facts_block(eligibility_matrix, requirements)
        answer = generate_answer(question, records, facts=facts, route="compare")
        citations = citations_from_answer(answer, records)
        return answer, citations
    except Exception:
        logger.exception("Comparison narrative generation failed")
        return None, []
