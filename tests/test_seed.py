from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.seed import SeedConfig, build_config_from_args, main, parse_args, seed_data
from backend.domain.enums import OrganizationType, UserRole
from backend.models import Employer, HealthcareProvider, Hospital, Organization, Plan, User


async def _counts(session: AsyncSession) -> dict[str, int]:
    async def count(model) -> int:
        result = await session.execute(select(func.count()).select_from(model))
        return result.scalar_one()

    return {
        "organizations": await count(Organization),
        "employers": await count(Employer),
        "providers": await count(HealthcareProvider),
        "hospitals": await count(Hospital),
        "plans": await count(Plan),
        "users": await count(User),
    }


async def test_demo_seed_creates_fixed_demo_accounts(seed_session: AsyncSession) -> None:
    await seed_data(seed_session, SeedConfig.demo(seed=1))

    result = await seed_session.execute(select(User).where(User.email == "employer@acme.com"))
    assert result.scalar_one_or_none() is not None

    result = await seed_session.execute(select(User).where(User.email == "platform@benefits.com"))
    assert result.scalar_one_or_none() is not None


async def test_demo_seed_generates_extra_variety_beyond_fixed_accounts(
    seed_session: AsyncSession,
) -> None:
    summary = await seed_data(seed_session, SeedConfig.demo(seed=2))

    # 1 fixed employer + N generated ones; 2 fixed providers + N generated ones.
    assert summary.employers > 1
    assert summary.healthcare_providers > 2

    counts = await _counts(seed_session)
    assert counts["organizations"] == summary.organizations
    assert counts["employers"] == summary.employers
    assert counts["providers"] == summary.healthcare_providers


async def test_demo_seed_includes_zero_plan_provider_edge_case(
    seed_session: AsyncSession,
) -> None:
    await seed_data(seed_session, SeedConfig.demo(seed=3))

    result = await seed_session.execute(
        select(HealthcareProvider.id)
        .outerjoin(Plan, Plan.provider_id == HealthcareProvider.id)
        .where(Plan.id.is_(None))
    )
    zero_plan_providers = result.scalars().all()
    assert len(zero_plan_providers) >= 1


async def test_seed_is_idempotent(seed_session: AsyncSession) -> None:
    config = SeedConfig.demo(seed=7)

    await seed_data(seed_session, config)
    before = await _counts(seed_session)

    await seed_data(seed_session, config)
    after = await _counts(seed_session)

    assert before == after
    assert before["organizations"] > 0


async def test_seed_referential_integrity(seed_session: AsyncSession) -> None:
    await seed_data(seed_session, SeedConfig.demo(seed=5))

    orgs = {
        row.id: row.org_type
        for row in (await seed_session.execute(select(Organization))).scalars().all()
    }

    employers = (await seed_session.execute(select(Employer))).scalars().all()
    assert employers
    for employer in employers:
        assert orgs[employer.organization_id] == OrganizationType.EMPLOYER

    providers = (await seed_session.execute(select(HealthcareProvider))).scalars().all()
    assert providers
    provider_ids = {p.id for p in providers}
    for provider in providers:
        assert orgs[provider.organization_id] == OrganizationType.HEALTHCARE_PROVIDER

    plans = (await seed_session.execute(select(Plan))).scalars().all()
    for plan in plans:
        assert plan.provider_id in provider_ids

    hospitals = (await seed_session.execute(select(Hospital))).scalars().all()
    for hospital in hospitals:
        assert hospital.provider_id in provider_ids

    users = (await seed_session.execute(select(User))).scalars().all()
    assert users
    for user in users:
        org_type = orgs[user.organization_id]
        if user.role == UserRole.EMPLOYER_ADMIN:
            assert org_type == OrganizationType.EMPLOYER
        elif user.role == UserRole.HEALTHCARE_ORG_ADMIN:
            assert org_type == OrganizationType.HEALTHCARE_PROVIDER


async def test_load_test_mode_generates_larger_volume_than_demo(
    seed_session: AsyncSession,
) -> None:
    demo_summary = await seed_data(seed_session, SeedConfig.demo(seed=9))

    load_config = SeedConfig.load_test(tenant_count=25, provider_count=10, seed=9)
    load_summary = await seed_data(seed_session, load_config)

    assert load_summary.employers == 25
    assert load_summary.healthcare_providers == 10
    assert load_summary.employers > demo_summary.employers
    assert load_summary.healthcare_providers > demo_summary.healthcare_providers


async def test_load_test_mode_excludes_fixed_demo_accounts(seed_session: AsyncSession) -> None:
    await seed_data(seed_session, SeedConfig.load_test(tenant_count=5, provider_count=2, seed=1))

    result = await seed_session.execute(select(User).where(User.email == "employer@acme.com"))
    assert result.scalar_one_or_none() is None


def test_parse_args_maps_tenant_count_and_provider_count_for_load_test() -> None:
    args = parse_args(
        [
            "--mode",
            "load-test",
            "--tenant-count",
            "500",
            "--provider-count",
            "50",
            "--seed",
            "42",
        ]
    )
    config = build_config_from_args(args)

    assert config.mode == "load_test"
    assert config.extra_employer_count == 500
    assert config.extra_provider_count == 50
    assert config.seed == 42
    assert config.include_fixed_demo_accounts is False


def test_parse_args_defaults_to_small_demo_config() -> None:
    args = parse_args([])
    config = build_config_from_args(args)

    assert config.mode == "demo"
    assert config.include_fixed_demo_accounts is True
    assert config.extra_employer_count <= 5
    assert config.extra_provider_count <= 5


async def test_cli_main_seeds_scratch_database(
    seed_session: AsyncSession, seed_database_url: str
) -> None:
    argv = [
        "--mode",
        "load-test",
        "--tenant-count",
        "4",
        "--provider-count",
        "2",
        "--seed",
        "3",
        "--database-url",
        seed_database_url,
    ]

    await asyncio.to_thread(main, argv)

    counts = await _counts(seed_session)
    assert counts["employers"] == 4
    assert counts["providers"] == 2
