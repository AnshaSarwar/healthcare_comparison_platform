from dataclasses import dataclass
from uuid import UUID

from backend.domain.enums import UserRole


@dataclass(frozen=True)
class SecurityContext:
    user_id: UUID
    role: UserRole
    organization_id: UUID


class AccessDeniedError(PermissionError):
    pass


def can_view_pricing(ctx: SecurityContext) -> bool:
    return ctx.role in (UserRole.PLATFORM_ADMIN, UserRole.HEALTHCARE_ORG_ADMIN)


def can_view_employer_data(ctx: SecurityContext, employer_org_id: UUID) -> bool:
    if ctx.role == UserRole.PLATFORM_ADMIN:
        return True
    if ctx.role == UserRole.EMPLOYER_ADMIN:
        return ctx.organization_id == employer_org_id
    return False


def can_view_provider_plans(ctx: SecurityContext, provider_org_id: UUID) -> bool:
    if ctx.role == UserRole.PLATFORM_ADMIN:
        return True
    if ctx.role == UserRole.HEALTHCARE_ORG_ADMIN:
        return ctx.organization_id == provider_org_id
    if ctx.role == UserRole.EMPLOYER_ADMIN:
        return True
    return False


def can_view_provider_pricing(ctx: SecurityContext, provider_org_id: UUID) -> bool:
    if ctx.role == UserRole.PLATFORM_ADMIN:
        return True
    if ctx.role == UserRole.HEALTHCARE_ORG_ADMIN:
        return ctx.organization_id == provider_org_id
    return False


def assert_employer_access(ctx: SecurityContext, employer_org_id: UUID) -> None:
    if not can_view_employer_data(ctx, employer_org_id):
        raise AccessDeniedError("Not authorized to access this employer's data")


def assert_comparison_access(ctx: SecurityContext, employer_org_id: UUID) -> None:
    if ctx.role not in (
        UserRole.PLATFORM_ADMIN,
        UserRole.EMPLOYER_ADMIN,
    ):
        raise AccessDeniedError("Not authorized to run comparisons")
    if ctx.role == UserRole.EMPLOYER_ADMIN and ctx.organization_id != employer_org_id:
        raise AccessDeniedError("Not authorized to access this employer's comparisons")


def can_manage_plan_documents(ctx: SecurityContext, provider_org_id: UUID) -> bool:
    if ctx.role == UserRole.PLATFORM_ADMIN:
        return True
    if ctx.role == UserRole.EMPLOYER_ADMIN:
        return True
    if ctx.role == UserRole.HEALTHCARE_ORG_ADMIN:
        return ctx.organization_id == provider_org_id
    return False


def can_manage_employer(ctx: SecurityContext, employer_org_id: UUID) -> bool:
    if ctx.role == UserRole.PLATFORM_ADMIN:
        return True
    if ctx.role == UserRole.EMPLOYER_ADMIN:
        return ctx.organization_id == employer_org_id
    return False


def can_manage_provider(ctx: SecurityContext, provider_org_id: UUID) -> bool:
    if ctx.role == UserRole.PLATFORM_ADMIN:
        return True
    if ctx.role == UserRole.HEALTHCARE_ORG_ADMIN:
        return ctx.organization_id == provider_org_id
    return False


def is_platform_admin(ctx: SecurityContext) -> bool:
    return ctx.role == UserRole.PLATFORM_ADMIN


def strip_pricing_from_plan(plan_dict: dict) -> dict:
    stripped = dict(plan_dict)
    stripped.pop("pricing_tiers", None)
    return stripped
