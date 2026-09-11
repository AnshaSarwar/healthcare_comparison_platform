from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import hash_password
from backend.domain.enums import CoverageType, OrganizationType, UserRole
from backend.models import Employer, HealthcareProvider, Hospital, Organization, Plan, User


async def seed_data(session: AsyncSession) -> None:
    existing = await session.execute(select(User).limit(1))
    if existing.scalar_one_or_none() is not None:
        return

    employer_org = Organization(name="Acme Manufacturing", org_type=OrganizationType.EMPLOYER)
    provider_a_org = Organization(name="HealthFirst Insurance", org_type=OrganizationType.HEALTHCARE_PROVIDER)
    provider_b_org = Organization(name="MediCare Plus", org_type=OrganizationType.HEALTHCARE_PROVIDER)
    session.add_all([employer_org, provider_a_org, provider_b_org])
    await session.flush()

    employer = Employer(
        organization_id=employer_org.id,
        name="Acme Manufacturing",
        demographics={
            "age_bands": [
                {"label": "25-34", "min_age": 25, "max_age": 34, "count": 80},
                {"label": "35-44", "min_age": 35, "max_age": 44, "count": 45},
                {"label": "45-54", "min_age": 45, "max_age": 54, "count": 25},
            ],
            "department_breakdown": {"Engineering": 60, "Operations": 50, "HR": 40},
            "total_dependents": 120,
            "role_tier_breakdown": {"staff": 100, "manager": 50},
        },
        requirements={
            "budget_ceiling_per_employee": 500.0,
            "must_have_coverage_types": ["opd_ipd"],
            "min_headcount": 50,
            "avg_age": 36.0,
            "maternity_required": True,
            "pre_existing_coverage_required": True,
        },
    )

    provider_a = HealthcareProvider(organization_id=provider_a_org.id, name="HealthFirst Insurance")
    provider_b = HealthcareProvider(organization_id=provider_b_org.id, name="MediCare Plus")
    session.add_all([employer, provider_a, provider_b])
    await session.flush()

    hospitals = [
        Hospital(provider_id=provider_a.id, name="City General", city="Karachi", tier="tier1"),
        Hospital(provider_id=provider_a.id, name="Metro Clinic", city="Lahore", tier="tier2"),
        Hospital(provider_id=provider_b.id, name="National Hospital", city="Islamabad", tier="tier1"),
    ]
    session.add_all(hospitals)

    plans = [
        Plan(
            provider_id=provider_a.id,
            name="HealthFirst Corporate OPD+IPD",
            coverage_type=CoverageType.OPD_IPD,
            terms={
                "waiting_period_days": 30,
                "exclusions": ["cosmetic surgery"],
                "sub_limits": {"dental": 15000},
                "maternity_coverage": True,
                "maternity_waiting_days": 180,
                "pre_existing_condition_rules": "Covered after 12 months",
                "min_employee_count": 25,
            },
            pricing_tiers=[
                {"age_band_label": "25-34", "monthly_premium_per_employee": 420.0},
                {"age_band_label": "35-44", "monthly_premium_per_employee": 480.0},
                {"age_band_label": "45-54", "monthly_premium_per_employee": 550.0},
            ],
        ),
        Plan(
            provider_id=provider_b.id,
            name="MediCare Essential IPD",
            coverage_type=CoverageType.IPD,
            terms={
                "waiting_period_days": 60,
                "exclusions": ["experimental treatment"],
                "sub_limits": {"room_rent": 8000},
                "maternity_coverage": False,
                "maternity_waiting_days": 0,
                "pre_existing_condition_rules": "",
                "min_employee_count": 50,
            },
            pricing_tiers=[
                {"age_band_label": "25-34", "monthly_premium_per_employee": 350.0},
                {"age_band_label": "35-44", "monthly_premium_per_employee": 390.0},
                {"age_band_label": "45-54", "monthly_premium_per_employee": 430.0},
            ],
        ),
        Plan(
            provider_id=provider_b.id,
            name="MediCare Premium OPD+IPD",
            coverage_type=CoverageType.OPD_IPD,
            terms={
                "waiting_period_days": 15,
                "exclusions": [],
                "sub_limits": {"dental": 25000, "optical": 10000},
                "maternity_coverage": True,
                "maternity_waiting_days": 90,
                "pre_existing_condition_rules": "Covered after 6 months",
                "min_employee_count": 30,
            },
            pricing_tiers=[
                {"age_band_label": "25-34", "monthly_premium_per_employee": 510.0},
                {"age_band_label": "35-44", "monthly_premium_per_employee": 560.0},
                {"age_band_label": "45-54", "monthly_premium_per_employee": 620.0},
            ],
        ),
    ]
    session.add_all(plans)

    users = [
        User(
            email="employer@acme.com",
            hashed_password=hash_password("password123"),
            role=UserRole.EMPLOYER_ADMIN,
            organization_id=employer_org.id,
        ),
        User(
            email="admin@healthfirst.com",
            hashed_password=hash_password("password123"),
            role=UserRole.HEALTHCARE_ORG_ADMIN,
            organization_id=provider_a_org.id,
        ),
        User(
            email="admin@medicare.com",
            hashed_password=hash_password("password123"),
            role=UserRole.HEALTHCARE_ORG_ADMIN,
            organization_id=provider_b_org.id,
        ),
        User(
            email="platform@benefits.com",
            hashed_password=hash_password("password123"),
            role=UserRole.PLATFORM_ADMIN,
            organization_id=employer_org.id,
        ),
    ]
    session.add_all(users)
    await session.commit()
