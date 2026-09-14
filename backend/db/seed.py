"""Seed data: a fixed demo dataset plus a configurable synthetic-tenant factory.

Two modes:
- demo: the original hand-authored Acme/HealthFirst/MediCare dataset (unchanged --
  other docs/scripts reference these exact emails) plus a small number of extra
  generated tenants for realistic variety.
- load_test: skips the fixed accounts and generates a large number of synthetic
  tenants for scale testing.

Both modes are idempotent: entities are keyed by a deterministic name (derived from
--seed and index), and re-running with the same config skips organizations that
already exist rather than duplicating them.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import itertools
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import get_settings
from backend.core.security import hash_password
from backend.domain.enums import CoverageType, OrganizationType, UserRole
from backend.models import Base, Employer, HealthcareProvider, Hospital, Organization, Plan, User

COVERAGE_TYPES: tuple[CoverageType, ...] = tuple(CoverageType)

_EMPLOYER_ADJECTIVES = [
    "Summit",
    "Blue Ridge",
    "Riverside",
    "Cedar",
    "Northgate",
    "Lakeside",
    "Union",
    "Harbor",
    "Frontier",
    "Meridian",
    "Golden Gate",
    "Silverline",
    "Ironwood",
    "Crestview",
    "Bayview",
]
_EMPLOYER_NOUNS = [
    "Manufacturing",
    "Logistics",
    "Textiles",
    "Foods",
    "Retail Group",
    "Technologies",
    "Construction",
    "Freight",
    "Apparel",
    "Electronics",
    "Analytics",
    "Consulting",
    "Energy",
    "Agri Co",
    "Motors",
]
_PROVIDER_ADJECTIVES = [
    "National",
    "Unity",
    "Prime",
    "Guardian",
    "Trustcare",
    "Wellspring",
    "Horizon",
    "Vitality",
    "Cornerstone",
    "Beacon",
]
_PROVIDER_NOUNS = [
    "Health Insurance",
    "Assurance",
    "Medical Trust",
    "Care Partners",
    "Wellness Group",
    "Mutual",
    "Health Plans",
    "Life & Health",
]
_CITIES: tuple[tuple[str, str], ...] = (
    ("Karachi", "tier1"),
    ("Lahore", "tier1"),
    ("Islamabad", "tier1"),
    ("Faisalabad", "tier2"),
    ("Multan", "tier2"),
    ("Peshawar", "tier2"),
    ("Quetta", "tier3"),
    ("Hyderabad", "tier3"),
)
_DEPARTMENTS = ["Engineering", "Operations", "HR", "Sales", "Finance", "Support", "Warehouse", "IT"]
_PLAN_TIERS = ["Essential", "Standard", "Corporate", "Premium", "Elite"]
_EXCLUSIONS = [
    "cosmetic surgery",
    "experimental treatment",
    "dental (non-emergency)",
    "fertility treatment",
]

SeedMode = Literal["demo", "load_test"]

DEMO_PASSWORD = "password123"


@dataclass(frozen=True)
class SeedConfig:
    mode: SeedMode = "demo"
    include_fixed_demo_accounts: bool = True
    extra_employer_count: int = 2
    extra_provider_count: int = 2
    min_plans_per_provider: int = 1
    max_plans_per_provider: int = 3
    zero_plan_providers: int = 1
    seed: int = 20240914
    name_prefix: str = "Demo"

    @classmethod
    def demo(cls, *, seed: int = 20240914) -> SeedConfig:
        return cls(
            mode="demo",
            include_fixed_demo_accounts=True,
            extra_employer_count=2,
            extra_provider_count=2,
            min_plans_per_provider=1,
            max_plans_per_provider=3,
            zero_plan_providers=1,
            seed=seed,
            name_prefix="Demo",
        )

    @classmethod
    def load_test(
        cls, *, tenant_count: int, provider_count: int | None = None, seed: int = 20240914
    ) -> SeedConfig:
        providers = provider_count if provider_count is not None else max(2, tenant_count // 5)
        zero_plan = max(1, providers // 10)
        return cls(
            mode="load_test",
            include_fixed_demo_accounts=False,
            extra_employer_count=tenant_count,
            extra_provider_count=providers,
            min_plans_per_provider=0,
            max_plans_per_provider=5,
            zero_plan_providers=min(zero_plan, providers),
            seed=seed,
            name_prefix="Load",
        )


@dataclass
class SeedSummary:
    organizations: int = 0
    employers: int = 0
    healthcare_providers: int = 0
    hospitals: int = 0
    plans: int = 0
    users: int = 0
    skipped_existing: int = 0


@dataclass(frozen=True)
class PlanSpec:
    name: str
    coverage_type: CoverageType
    terms: dict
    pricing_tiers: list


@dataclass(frozen=True)
class EmployerSpec:
    org_name: str
    admin_email: str
    demographics: dict
    requirements: dict


@dataclass(frozen=True)
class ProviderSpec:
    org_name: str
    admin_email: str
    hospitals: list[tuple[str, str, str]] = field(default_factory=list)
    plans: list[PlanSpec] = field(default_factory=list)


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("&", "and")


def _generate_employer_spec(rng: random.Random, index: int, prefix: str) -> EmployerSpec:
    adjective = rng.choice(_EMPLOYER_ADJECTIVES)
    noun = rng.choice(_EMPLOYER_NOUNS)
    org_name = f"{prefix} {adjective} {noun} {index:04d}"
    admin_email = f"admin-{_slug(org_name)}@example-employer.test"

    age_bands = []
    total_headcount = 0
    for label, lo, hi in (("22-30", 22, 30), ("31-40", 31, 40), ("41-55", 41, 55)):
        count = rng.randint(10, 120)
        age_bands.append({"label": label, "min_age": lo, "max_age": hi, "count": count})
        total_headcount += count

    departments = rng.sample(_DEPARTMENTS, k=min(4, len(_DEPARTMENTS)))
    demographics = {
        "age_bands": age_bands,
        "department_breakdown": {dept: rng.randint(5, 60) for dept in departments},
        "total_dependents": rng.randint(0, total_headcount),
        "role_tier_breakdown": {
            "staff": int(total_headcount * 0.7),
            "manager": int(total_headcount * 0.3),
        },
    }
    coverage_values = [c.value for c in COVERAGE_TYPES]
    requirements = {
        "budget_ceiling_per_employee": round(rng.uniform(250.0, 700.0), 2),
        "must_have_coverage_types": rng.sample(
            coverage_values, k=rng.randint(1, len(coverage_values))
        ),
        "min_headcount": max(1, total_headcount // 2),
        "avg_age": round(rng.uniform(28.0, 48.0), 1),
        "maternity_required": rng.random() < 0.5,
        "pre_existing_coverage_required": rng.random() < 0.5,
    }
    return EmployerSpec(
        org_name=org_name,
        admin_email=admin_email,
        demographics=demographics,
        requirements=requirements,
    )


def _generate_plan_spec(
    rng: random.Random, provider_name: str, index: int, coverage_type: CoverageType
) -> PlanSpec:
    tier_label = rng.choice(_PLAN_TIERS)
    name = f"{provider_name} {tier_label} {coverage_type.value.upper()} {index + 1}"
    base_premium = rng.uniform(250.0, 700.0)
    pricing_tiers = [
        {
            "age_band_label": label,
            "monthly_premium_per_employee": round(base_premium * multiplier, 2),
        }
        for label, multiplier in (("22-30", 1.0), ("31-40", 1.12), ("41-55", 1.28))
    ]
    terms = {
        "waiting_period_days": rng.choice([0, 15, 30, 60, 90]),
        "exclusions": rng.sample(_EXCLUSIONS, k=rng.randint(0, 2)),
        "sub_limits": {"room_rent": rng.choice([5000, 8000, 12000, 20000])},
        "maternity_coverage": coverage_type != CoverageType.IPD and rng.random() < 0.7,
        "maternity_waiting_days": rng.choice([0, 90, 180]),
        "pre_existing_condition_rules": rng.choice(
            ["", "Covered after 6 months", "Covered after 12 months", "Not covered"]
        ),
        "min_employee_count": rng.choice([10, 25, 50, 100]),
    }
    return PlanSpec(
        name=name, coverage_type=coverage_type, terms=terms, pricing_tiers=pricing_tiers
    )


def _generate_provider_spec(
    rng: random.Random, index: int, prefix: str, plan_count: int
) -> ProviderSpec:
    adjective = rng.choice(_PROVIDER_ADJECTIVES)
    noun = rng.choice(_PROVIDER_NOUNS)
    org_name = f"{prefix} {adjective} {noun} {index:04d}"
    admin_email = f"admin-{_slug(org_name)}@example-provider.test"

    hospital_count = rng.randint(1, 3)
    hospitals: list[tuple[str, str, str]] = []
    for h in range(hospital_count):
        city, tier = rng.choice(_CITIES)
        hospitals.append((f"{adjective} {city} Hospital {h + 1}", city, tier))

    coverage_cycle = itertools.cycle(COVERAGE_TYPES)
    plans = [_generate_plan_spec(rng, org_name, p, next(coverage_cycle)) for p in range(plan_count)]
    return ProviderSpec(
        org_name=org_name, admin_email=admin_email, hospitals=hospitals, plans=plans
    )


async def _get_or_create_org(
    session: AsyncSession, name: str, org_type: OrganizationType
) -> tuple[Organization, bool]:
    result = await session.execute(select(Organization).where(Organization.name == name))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False
    org = Organization(name=name, org_type=org_type)
    session.add(org)
    await session.flush()
    return org, True


async def _materialize_employer(
    session: AsyncSession, spec: EmployerSpec, password_hash: str, summary: SeedSummary
) -> None:
    org, created = await _get_or_create_org(session, spec.org_name, OrganizationType.EMPLOYER)
    if not created:
        summary.skipped_existing += 1
        return
    summary.organizations += 1
    session.add(
        Employer(
            organization_id=org.id,
            name=spec.org_name,
            demographics=spec.demographics,
            requirements=spec.requirements,
        )
    )
    session.add(
        User(
            email=spec.admin_email,
            hashed_password=password_hash,
            role=UserRole.EMPLOYER_ADMIN,
            organization_id=org.id,
            email_verified=True,
        )
    )
    summary.employers += 1
    summary.users += 1


async def _materialize_provider(
    session: AsyncSession, spec: ProviderSpec, password_hash: str, summary: SeedSummary
) -> None:
    org, created = await _get_or_create_org(
        session, spec.org_name, OrganizationType.HEALTHCARE_PROVIDER
    )
    if not created:
        summary.skipped_existing += 1
        return
    summary.organizations += 1
    provider = HealthcareProvider(organization_id=org.id, name=spec.org_name)
    session.add(provider)
    await session.flush()
    summary.healthcare_providers += 1

    session.add(
        User(
            email=spec.admin_email,
            hashed_password=password_hash,
            role=UserRole.HEALTHCARE_ORG_ADMIN,
            organization_id=org.id,
            email_verified=True,
        )
    )
    summary.users += 1

    for name, city, tier in spec.hospitals:
        session.add(Hospital(provider_id=provider.id, name=name, city=city, tier=tier))
        summary.hospitals += 1

    for plan_spec in spec.plans:
        session.add(
            Plan(
                provider_id=provider.id,
                name=plan_spec.name,
                coverage_type=plan_spec.coverage_type,
                terms=plan_spec.terms,
                pricing_tiers=plan_spec.pricing_tiers,
            )
        )
        summary.plans += 1


async def _seed_fixed_demo_accounts(
    session: AsyncSession, password_hash: str, summary: SeedSummary
) -> None:
    """The original hand-authored Acme/HealthFirst/MediCare dataset.

    Emails here are documented in CLAUDE.md and used by manual QA / smoke scripts --
    keep them exactly as-is.
    """
    employer_org, employer_created = await _get_or_create_org(
        session, "Acme Manufacturing", OrganizationType.EMPLOYER
    )
    provider_a_org, provider_a_created = await _get_or_create_org(
        session, "HealthFirst Insurance", OrganizationType.HEALTHCARE_PROVIDER
    )
    provider_b_org, provider_b_created = await _get_or_create_org(
        session, "MediCare Plus", OrganizationType.HEALTHCARE_PROVIDER
    )

    if employer_created:
        summary.organizations += 1
        session.add(
            Employer(
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
        )
        session.add(
            User(
                email="employer@acme.com",
                hashed_password=password_hash,
                role=UserRole.EMPLOYER_ADMIN,
                organization_id=employer_org.id,
                email_verified=True,
            )
        )
        session.add(
            User(
                email="platform@benefits.com",
                hashed_password=password_hash,
                role=UserRole.PLATFORM_ADMIN,
                organization_id=employer_org.id,
                email_verified=True,
            )
        )
        summary.employers += 1
        summary.users += 2
    else:
        summary.skipped_existing += 1

    await session.flush()

    if provider_a_created:
        summary.organizations += 1
        provider_a = HealthcareProvider(
            organization_id=provider_a_org.id, name="HealthFirst Insurance"
        )
        session.add(provider_a)
        await session.flush()
        session.add(
            Hospital(provider_id=provider_a.id, name="City General", city="Karachi", tier="tier1")
        )
        session.add(
            Hospital(provider_id=provider_a.id, name="Metro Clinic", city="Lahore", tier="tier2")
        )
        session.add(
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
            )
        )
        session.add(
            User(
                email="admin@healthfirst.com",
                hashed_password=password_hash,
                role=UserRole.HEALTHCARE_ORG_ADMIN,
                organization_id=provider_a_org.id,
                email_verified=True,
            )
        )
        summary.healthcare_providers += 1
        summary.hospitals += 2
        summary.plans += 1
        summary.users += 1
    else:
        summary.skipped_existing += 1

    if provider_b_created:
        summary.organizations += 1
        provider_b = HealthcareProvider(organization_id=provider_b_org.id, name="MediCare Plus")
        session.add(provider_b)
        await session.flush()
        session.add(
            Hospital(
                provider_id=provider_b.id, name="National Hospital", city="Islamabad", tier="tier1"
            )
        )
        session.add(
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
            )
        )
        session.add(
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
            )
        )
        session.add(
            User(
                email="admin@medicare.com",
                hashed_password=password_hash,
                role=UserRole.HEALTHCARE_ORG_ADMIN,
                organization_id=provider_b_org.id,
                email_verified=True,
            )
        )
        summary.healthcare_providers += 1
        summary.hospitals += 1
        summary.plans += 2
        summary.users += 1
    else:
        summary.skipped_existing += 1


async def seed_data(session: AsyncSession, config: SeedConfig | None = None) -> SeedSummary:
    config = config or SeedConfig.demo()
    summary = SeedSummary()
    password_hash = hash_password(DEMO_PASSWORD)

    if config.include_fixed_demo_accounts:
        await _seed_fixed_demo_accounts(session, password_hash, summary)

    rng = random.Random(config.seed)
    zero_plan_start = config.extra_provider_count - config.zero_plan_providers
    zero_plan_indexes = set(range(max(zero_plan_start, 0), config.extra_provider_count))

    for i in range(config.extra_employer_count):
        spec = _generate_employer_spec(rng, i, config.name_prefix)
        await _materialize_employer(session, spec, password_hash, summary)

    for i in range(config.extra_provider_count):
        if i in zero_plan_indexes:
            plan_count = 0
        else:
            plan_count = rng.randint(config.min_plans_per_provider, config.max_plans_per_provider)
        spec = _generate_provider_spec(rng, i, config.name_prefix, plan_count)
        await _materialize_provider(session, spec, password_hash, summary)

    await session.commit()
    return summary


async def _run_async(config: SeedConfig, database_url: str, create_tables: bool) -> SeedSummary:
    engine = create_async_engine(database_url)
    try:
        if create_tables:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            return await seed_data(session, config)
    finally:
        await engine.dispose()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo or load-test tenant data")
    parser.add_argument("--mode", choices=["demo", "load-test"], default="demo")
    parser.add_argument(
        "--tenant-count",
        type=int,
        default=None,
        help="Number of extra employer tenants to generate (demo default: 2, load-test default: 500)",
    )
    parser.add_argument(
        "--provider-count",
        type=int,
        default=None,
        help="Number of extra healthcare-provider tenants to generate",
    )
    parser.add_argument(
        "--seed", type=int, default=20240914, help="RNG seed for reproducible synthetic data"
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override Settings.database_url (e.g. to target a scratch DB)",
    )
    parser.add_argument(
        "--create-tables",
        action="store_true",
        help=(
            "Run create_all before seeding. Only use against a scratch/dev DB -- "
            "never against a DB managed by Alembic."
        ),
    )
    return parser.parse_args(argv)


def build_config_from_args(args: argparse.Namespace) -> SeedConfig:
    if args.mode == "demo":
        config = SeedConfig.demo(seed=args.seed)
        overrides: dict = {}
        if args.tenant_count is not None:
            overrides["extra_employer_count"] = args.tenant_count
        if args.provider_count is not None:
            overrides["extra_provider_count"] = args.provider_count
        if overrides:
            config = dataclasses.replace(config, **overrides)
        return config

    tenant_count = args.tenant_count if args.tenant_count is not None else 500
    return SeedConfig.load_test(
        tenant_count=tenant_count, provider_count=args.provider_count, seed=args.seed
    )


def main(argv: Sequence[str] | None = None) -> SeedSummary:
    args = parse_args(argv)
    config = build_config_from_args(args)
    database_url = args.database_url or get_settings().database_url
    summary = asyncio.run(_run_async(config, database_url, args.create_tables))
    print(f"Seed complete ({config.mode}): {summary}")
    return summary


if __name__ == "__main__":
    main()
