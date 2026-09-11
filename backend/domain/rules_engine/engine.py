from dataclasses import dataclass
from statistics import mean
from uuid import UUID

from backend.domain.enums import CoverageType, EligibilityOutcome
from backend.schemas import (
    EligibilityRuleResult,
    EmployeeDemographics,
    EmployerRequirements,
    PlanEligibilityResult,
    PlanTerms,
    PricingTier,
)


@dataclass
class PlanInput:
    plan_id: UUID
    plan_name: str
    provider_organization_id: UUID
    coverage_type: CoverageType
    terms: PlanTerms
    pricing_tiers: list[PricingTier]
    network_hospital_count: int
    provider_name: str = ""


@dataclass
class ComparisonWeights:
    cost: float = 0.4
    coverage: float = 0.35
    network: float = 0.25

    def __post_init__(self) -> None:
        total = self.cost + self.coverage + self.network
        if abs(total - 1.0) > 0.001:
            raise ValueError("Weights must sum to 1.0")


def _coverage_matches(required: CoverageType, offered: CoverageType) -> bool:
    if required == CoverageType.OPD_IPD:
        return offered == CoverageType.OPD_IPD
    if required == CoverageType.OPD:
        return offered in (CoverageType.OPD, CoverageType.OPD_IPD)
    if required == CoverageType.IPD:
        return offered in (CoverageType.IPD, CoverageType.OPD_IPD)
    return False


def _estimate_monthly_cost(demographics: EmployeeDemographics, tiers: list[PricingTier]) -> float | None:
    if not tiers or demographics.headcount == 0:
        return None

    tier_map = {t.age_band_label: t.monthly_premium_per_employee for t in tiers}
    total = 0.0
    matched = 0

    for band in demographics.age_bands:
        premium = tier_map.get(band.label)
        if premium is None:
            premiums = [t.monthly_premium_per_employee for t in tiers]
            premium = mean(premiums) if premiums else 0.0
        total += premium * band.count
        matched += band.count

    if matched == 0:
        avg_premium = mean(t.monthly_premium_per_employee for t in tiers)
        return avg_premium * demographics.headcount
    return total


def evaluate_plan(
    plan: PlanInput,
    demographics: EmployeeDemographics,
    requirements: EmployerRequirements,
) -> PlanEligibilityResult:
    rules: list[EligibilityRuleResult] = []

    headcount = demographics.headcount
    rules.append(
        EligibilityRuleResult(
            rule_id="min_headcount",
            rule_name="Minimum headcount",
            outcome=EligibilityOutcome.PASS
            if headcount >= requirements.min_headcount
            else EligibilityOutcome.FAIL,
            message=f"Employer headcount {headcount} vs required minimum {requirements.min_headcount}",
            details={"headcount": headcount, "required": requirements.min_headcount},
        )
    )

    rules.append(
        EligibilityRuleResult(
            rule_id="plan_min_employees",
            rule_name="Plan minimum employee count",
            outcome=EligibilityOutcome.PASS
            if headcount >= plan.terms.min_employee_count
            else EligibilityOutcome.FAIL,
            message=(
                f"Employer headcount {headcount} vs plan minimum {plan.terms.min_employee_count}"
            ),
            details={"headcount": headcount, "plan_minimum": plan.terms.min_employee_count},
        )
    )

    for required_coverage in requirements.must_have_coverage_types:
        passed = _coverage_matches(required_coverage, plan.coverage_type)
        rules.append(
            EligibilityRuleResult(
                rule_id=f"coverage_{required_coverage.value}",
                rule_name=f"Required coverage: {required_coverage.value.upper()}",
                outcome=EligibilityOutcome.PASS if passed else EligibilityOutcome.FAIL,
                message=(
                    f"Plan offers {plan.coverage_type.value}; "
                    f"required {required_coverage.value}"
                ),
                details={
                    "required": required_coverage.value,
                    "offered": plan.coverage_type.value,
                },
            )
        )

    estimated_cost = _estimate_monthly_cost(demographics, plan.pricing_tiers)
    per_employee_cost = (
        estimated_cost / headcount if estimated_cost is not None and headcount > 0 else None
    )
    if per_employee_cost is not None:
        budget_ok = per_employee_cost <= requirements.budget_ceiling_per_employee
        rules.append(
            EligibilityRuleResult(
                rule_id="budget_ceiling",
                rule_name="Budget ceiling per employee",
                outcome=EligibilityOutcome.PASS if budget_ok else EligibilityOutcome.FAIL,
                message=(
                    f"Estimated {per_employee_cost:.2f}/employee vs ceiling "
                    f"{requirements.budget_ceiling_per_employee:.2f}"
                ),
                details={
                    "estimated_per_employee": per_employee_cost,
                    "ceiling": requirements.budget_ceiling_per_employee,
                    "estimated_monthly_total": estimated_cost,
                },
            )
        )

    if requirements.maternity_required:
        maternity_ok = plan.terms.maternity_coverage
        rules.append(
            EligibilityRuleResult(
                rule_id="maternity_coverage",
                rule_name="Maternity coverage required",
                outcome=EligibilityOutcome.PASS if maternity_ok else EligibilityOutcome.FAIL,
                message="Maternity coverage included" if maternity_ok else "No maternity coverage",
                details={"maternity_coverage": plan.terms.maternity_coverage},
            )
        )

    if requirements.pre_existing_coverage_required:
        pec_ok = bool(plan.terms.pre_existing_condition_rules.strip())
        rules.append(
            EligibilityRuleResult(
                rule_id="pre_existing_coverage",
                rule_name="Pre-existing condition coverage",
                outcome=EligibilityOutcome.PASS if pec_ok else EligibilityOutcome.FAIL,
                message=(
                    plan.terms.pre_existing_condition_rules
                    if pec_ok
                    else "No pre-existing condition rules defined"
                ),
                details={"rules": plan.terms.pre_existing_condition_rules},
            )
        )

    fail_count = sum(1 for r in rules if r.outcome == EligibilityOutcome.FAIL)
    if fail_count == 0:
        overall = EligibilityOutcome.PASS
    elif fail_count == len(rules):
        overall = EligibilityOutcome.FAIL
    else:
        overall = EligibilityOutcome.PARTIAL

    return PlanEligibilityResult(
        plan_id=plan.plan_id,
        plan_name=plan.plan_name,
        provider_organization_id=plan.provider_organization_id,
        provider_name=plan.provider_name,
        overall_outcome=overall,
        rules=rules,
        estimated_monthly_cost=estimated_cost,
    )


def score_plan(
    result: PlanEligibilityResult,
    plan: PlanInput,
    requirements: EmployerRequirements,
    weights: ComparisonWeights | None = None,
) -> PlanEligibilityResult:
    weights = weights or ComparisonWeights()

    eligibility_score = 1.0 if result.overall_outcome == EligibilityOutcome.PASS else (
        0.5 if result.overall_outcome == EligibilityOutcome.PARTIAL else 0.0
    )

    headcount = max(
        sum(r.details.get("headcount", 0) for r in result.rules if r.rule_id == "min_headcount"),
        1,
    )
    per_employee = (
        result.estimated_monthly_cost / headcount
        if result.estimated_monthly_cost
        else requirements.budget_ceiling_per_employee
    )
    cost_ratio = min(per_employee / requirements.budget_ceiling_per_employee, 1.0)
    cost_score = 1.0 - cost_ratio

    coverage_score = eligibility_score
    network_score = min(plan.network_hospital_count / 50.0, 1.0)

    breakdown = {
        "cost": round(cost_score * weights.cost, 4),
        "coverage": round(coverage_score * weights.coverage, 4),
        "network": round(network_score * weights.network, 4),
        "eligibility_multiplier": eligibility_score,
    }
    total = round(sum(breakdown[k] for k in ("cost", "coverage", "network")), 4)

    result.score_breakdown = breakdown
    result.total_score = total if eligibility_score > 0 else 0.0
    return result


def run_comparison(
    plans: list[PlanInput],
    demographics: EmployeeDemographics,
    requirements: EmployerRequirements,
    weights: ComparisonWeights | None = None,
) -> tuple[list[PlanEligibilityResult], list[UUID], dict]:
    results: list[PlanEligibilityResult] = []
    audit_rules: list[dict] = []

    for plan in plans:
        eligibility = evaluate_plan(plan, demographics, requirements)
        scored = score_plan(eligibility, plan, requirements, weights)
        results.append(scored)
        audit_rules.append(
            {
                "plan_id": str(plan.plan_id),
                "rules_evaluated": [r.model_dump() for r in scored.rules],
                "score_breakdown": scored.score_breakdown,
            }
        )

    ranked = sorted(results, key=lambda r: r.total_score, reverse=True)
    ranking_ids = [r.plan_id for r in ranked]

    audit_trace = {
        "engine_version": "1.0.0",
        "weights": (weights or ComparisonWeights()).__dict__,
        "demographics_headcount": demographics.headcount,
        "requirements": requirements.model_dump(),
        "plan_evaluations": audit_rules,
    }
    return results, ranking_ids, audit_trace
