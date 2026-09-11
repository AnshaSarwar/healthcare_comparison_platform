from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.domain.enums import CoverageType, PolicyReviewStatus, UserRole
from backend.models import Plan, PlanVersion
from backend.services.plan import active_plan_version


def _version(
    label: str,
    status: PolicyReviewStatus,
    effective_from: datetime | None,
    effective_to: datetime | None = None,
) -> PlanVersion:
    return PlanVersion(
        id=uuid4(),
        plan_id=uuid4(),
        version_label=label,
        coverage_type=CoverageType.OPD_IPD,
        effective_from=effective_from,
        effective_to=effective_to,
        review_status=status,
        raw_terms={},
        normalized_terms={},
        pricing_tiers=[],
    )


def test_active_plan_version_uses_latest_approved_effective_version() -> None:
    now = datetime.now(timezone.utc)
    plan = Plan(id=uuid4(), provider_id=uuid4(), name="Plan", coverage_type=CoverageType.OPD_IPD)
    old = _version("old", PolicyReviewStatus.APPROVED, now - timedelta(days=30))
    current = _version("current", PolicyReviewStatus.APPROVED, now - timedelta(days=2))
    draft = _version("draft", PolicyReviewStatus.DRAFT, now - timedelta(days=1))
    future = _version("future", PolicyReviewStatus.APPROVED, now + timedelta(days=1))
    expired = _version(
        "expired",
        PolicyReviewStatus.APPROVED,
        now - timedelta(days=60),
        now - timedelta(days=31),
    )
    plan.versions = [old, current, draft, future, expired]

    assert active_plan_version(plan, now) is current


def test_plan_version_records_who_imported_the_source() -> None:
    importer_id = uuid4()
    importer_org_id = uuid4()
    version = PlanVersion(
        id=uuid4(),
        plan_id=uuid4(),
        version_label="Imported booklet.pdf",
        coverage_type=CoverageType.OPD_IPD,
        review_status=PolicyReviewStatus.NEEDS_REVIEW,
        raw_terms={},
        normalized_terms={},
        pricing_tiers=[],
        imported_by_user_id=importer_id,
        imported_by_org_id=importer_org_id,
        imported_by_role=UserRole.EMPLOYER_ADMIN,
    )

    assert version.imported_by_user_id == importer_id
    assert version.imported_by_org_id == importer_org_id
    assert version.imported_by_role == UserRole.EMPLOYER_ADMIN
