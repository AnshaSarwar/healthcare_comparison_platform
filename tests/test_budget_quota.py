"""Budget ceiling calculations against demo seed plan pricing."""

import pytest
from uuid import uuid4

from backend.domain.enums import CoverageType, EligibilityOutcome
from backend.domain.rules_engine.engine import evaluate_plan, run_comparison, score_plan
from backend.schemas import AgeBand, EmployeeDemographics, EmployerRequirements, PlanTerms, PricingTier
from backend.domain.rules_engine.engine import PlanInput


def _acme_demographics() -> EmployeeDemographics:
    return EmployeeDemographics(
        age_bands=[
            AgeBand(label="25-34", min_age=25, max_age=34, count=80),
            AgeBand(label="35-44", min_age=35, max_age=44, count=45),
            AgeBand(label="45-54", min_age=45, max_age=54, count=25),
        ]
    )


def _acme_requirements() -> EmployerRequirements:
    return EmployerRequirements(
        budget_ceiling_per_employee=500.0,
        must_have_coverage_types=[CoverageType.OPD_IPD],
        min_headcount=50,
        maternity_required=True,
        pre_existing_coverage_required=True,
    )


def _seed_plan(name: str, coverage: CoverageType, tiers: list[tuple[str, float]], **terms) -> PlanInput:
    default_terms = {
        "waiting_period_days": 30,
        "maternity_coverage": True,
        "pre_existing_condition_rules": "Covered",
        "min_employee_count": 25,
    }
    default_terms.update(terms)
    return PlanInput(
        plan_id=uuid4(),
        plan_name=name,
        provider_organization_id=uuid4(),
        coverage_type=coverage,
        terms=PlanTerms(**default_terms),
        pricing_tiers=[
            PricingTier(age_band_label=label, monthly_premium_per_employee=premium)
            for label, premium in tiers
        ],
        network_hospital_count=2,
    )


class TestSeedBudgetMath:
    def test_healthfirst_within_ceiling(self):
        plan = _seed_plan(
            "HealthFirst Corporate OPD+IPD",
            CoverageType.OPD_IPD,
            [("25-34", 420.0), ("35-44", 480.0), ("45-54", 550.0)],
        )
        result = evaluate_plan(plan, _acme_demographics(), _acme_requirements())
        budget = next(r for r in result.rules if r.rule_id == "budget_ceiling")
        # 80*420 + 45*480 + 25*550 = 68950 / 150 = 459.67
        assert budget.details["estimated_per_employee"] == pytest.approx(459.67, abs=0.01)
        assert budget.details["estimated_monthly_total"] == 68950.0
        assert budget.outcome == EligibilityOutcome.PASS

    def test_medicare_premium_over_ceiling(self):
        plan = _seed_plan(
            "MediCare Premium OPD+IPD",
            CoverageType.OPD_IPD,
            [("25-34", 510.0), ("35-44", 560.0), ("45-54", 620.0)],
            pre_existing_condition_rules="Covered after 6 months",
            min_employee_count=30,
        )
        result = evaluate_plan(plan, _acme_demographics(), _acme_requirements())
        budget = next(r for r in result.rules if r.rule_id == "budget_ceiling")
        # 81500 / 150 = 543.33
        assert budget.details["estimated_per_employee"] == pytest.approx(543.33, abs=0.01)
        assert budget.outcome == EligibilityOutcome.FAIL

    def test_ranking_favors_in_budget_plan(self):
        healthfirst = _seed_plan(
            "HealthFirst",
            CoverageType.OPD_IPD,
            [("25-34", 420.0), ("35-44", 480.0), ("45-54", 550.0)],
        )
        premium = _seed_plan(
            "MediCare Premium",
            CoverageType.OPD_IPD,
            [("25-34", 510.0), ("35-44", 560.0), ("45-54", 620.0)],
            pre_existing_condition_rules="Covered after 6 months",
            min_employee_count=30,
        )
        demo = _acme_demographics()
        reqs = _acme_requirements()
        results, ranking, _ = run_comparison([premium, healthfirst], demo, reqs)
        by_id = {r.plan_id: r for r in results}
        assert ranking[0] == healthfirst.plan_id
        assert by_id[healthfirst.plan_id].total_score > by_id[premium.plan_id].total_score

    def test_cost_score_higher_when_closer_to_ceiling(self):
        cheaper = _seed_plan("Cheap", CoverageType.OPD_IPD, [("25-34", 300.0), ("35-44", 340.0), ("45-54", 380.0)])
        pricier = _seed_plan("Pricier", CoverageType.OPD_IPD, [("25-34", 420.0), ("35-44", 480.0), ("45-54", 550.0)])
        reqs = _acme_requirements()
        cheap_score = score_plan(evaluate_plan(cheaper, _acme_demographics(), reqs), cheaper, reqs).score_breakdown["cost"]
        pricey_score = score_plan(evaluate_plan(pricier, _acme_demographics(), reqs), pricier, reqs).score_breakdown["cost"]
        assert cheap_score > pricey_score
