from uuid import uuid4

import pytest

from backend.domain.enums import CoverageType, EligibilityOutcome
from backend.domain.rules_engine.engine import (
    ComparisonWeights,
    PlanInput,
    evaluate_plan,
    run_comparison,
    score_plan,
)
from backend.schemas import (
    AgeBand,
    EmployeeDemographics,
    EmployerRequirements,
    PlanTerms,
    PricingTier,
)


def _demographics(counts: dict[str, int] | None = None) -> EmployeeDemographics:
    bands = counts or {"25-34": 80, "35-44": 45, "45-54": 25}
    return EmployeeDemographics(
        age_bands=[
            AgeBand(label=label, min_age=25, max_age=54, count=count)
            for label, count in bands.items()
        ]
    )


def _requirements(**overrides) -> EmployerRequirements:
    base = dict(
        budget_ceiling_per_employee=500.0,
        must_have_coverage_types=[CoverageType.OPD_IPD],
        min_headcount=50,
        maternity_required=True,
        pre_existing_coverage_required=True,
    )
    base.update(overrides)
    return EmployerRequirements(**base)


def _plan(
    *,
    name: str = "Good Plan",
    coverage: CoverageType = CoverageType.OPD_IPD,
    maternity: bool = True,
    pec: str = "Covered after 12 months",
    min_employees: int = 25,
    premium: float = 420.0,
    hospitals: int = 20,
) -> PlanInput:
    return PlanInput(
        plan_id=uuid4(),
        plan_name=name,
        provider_organization_id=uuid4(),
        coverage_type=coverage,
        terms=PlanTerms(
            waiting_period_days=30,
            maternity_coverage=maternity,
            pre_existing_condition_rules=pec,
            min_employee_count=min_employees,
        ),
        pricing_tiers=[
            PricingTier(age_band_label="25-34", monthly_premium_per_employee=premium),
            PricingTier(age_band_label="35-44", monthly_premium_per_employee=premium + 40),
            PricingTier(age_band_label="45-54", monthly_premium_per_employee=premium + 80),
        ],
        network_hospital_count=hospitals,
    )


class TestCoverageMatching:
    def test_opd_ipd_requires_exact_match(self):
        plan = _plan(coverage=CoverageType.IPD)
        result = evaluate_plan(plan, _demographics(), _requirements())
        coverage_rules = [r for r in result.rules if r.rule_id.startswith("coverage_")]
        assert coverage_rules
        assert coverage_rules[0].outcome == EligibilityOutcome.FAIL

    def test_opd_satisfied_by_opd_ipd(self):
        plan = _plan(coverage=CoverageType.OPD_IPD)
        result = evaluate_plan(
            plan,
            _demographics(),
            _requirements(must_have_coverage_types=[CoverageType.OPD], maternity_required=False),
        )
        coverage_rules = [r for r in result.rules if r.rule_id.startswith("coverage_")]
        assert coverage_rules[0].outcome == EligibilityOutcome.PASS


class TestEvaluatePlan:
    def test_full_pass_plan(self):
        result = evaluate_plan(_plan(), _demographics(), _requirements())
        assert result.overall_outcome == EligibilityOutcome.PASS
        assert result.estimated_monthly_cost is not None
        assert result.estimated_monthly_cost > 0

    def test_partial_when_some_rules_fail(self):
        plan = _plan(coverage=CoverageType.IPD, maternity=False)
        result = evaluate_plan(plan, _demographics(), _requirements())
        assert result.overall_outcome == EligibilityOutcome.PARTIAL
        failed = {r.rule_id for r in result.rules if r.outcome == EligibilityOutcome.FAIL}
        assert "coverage_opd_ipd" in failed
        assert "maternity_coverage" in failed

    def test_budget_rule_fails_when_over_ceiling(self):
        plan = _plan(premium=900.0)
        result = evaluate_plan(plan, _demographics(), _requirements(budget_ceiling_per_employee=500.0))
        budget = next(r for r in result.rules if r.rule_id == "budget_ceiling")
        assert budget.outcome == EligibilityOutcome.FAIL

    def test_pre_existing_fails_on_blank_rules(self):
        plan = _plan(pec="   ")
        result = evaluate_plan(plan, _demographics(), _requirements())
        pec = next(r for r in result.rules if r.rule_id == "pre_existing_coverage")
        assert pec.outcome == EligibilityOutcome.FAIL


class TestScoringAndRanking:
    def test_full_fail_zeros_total_score(self):
        plan = _plan(
            coverage=CoverageType.IPD,
            maternity=False,
            pec="",
            min_employees=200,
            premium=900.0,
        )
        demo = _demographics({"25-34": 5})
        eligibility = evaluate_plan(plan, demo, _requirements())
        scored = score_plan(eligibility, plan, _requirements())
        assert scored.overall_outcome == EligibilityOutcome.FAIL
        assert scored.total_score == 0.0

    def test_cheaper_plan_ranks_higher_when_both_pass(self):
        cheap = _plan(name="Cheap", premium=300.0, hospitals=10)
        pricey = _plan(name="Pricey", premium=450.0, hospitals=10)
        demo = _demographics()
        reqs = _requirements()
        _, ranking, audit = run_comparison([pricey, cheap], demo, reqs)
        assert ranking[0] == cheap.plan_id
        assert audit["engine_version"] == "1.0.0"

    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValueError, match="Weights must sum"):
            ComparisonWeights(cost=0.5, coverage=0.5, network=0.5)
