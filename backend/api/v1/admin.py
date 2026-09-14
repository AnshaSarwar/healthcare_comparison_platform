from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_security_context
from backend.api.v1.auth import set_auth_cookies
from backend.core.policies import AccessDeniedError, SecurityContext
from backend.core.rate_limit import limiter, setting_limit
from backend.core.security import create_access_token, issue_refresh_token
from backend.schemas import (
    EmployerRead,
    OrganizationRead,
    PlanRead,
    PlanVersionCreateRequest,
    PlanVersionRead,
    PlanVersionReviewRequest,
    TokenResponse,
    UserRead,
)
from backend.schemas.admin import (
    EmployerUpdateRequest,
    HospitalCreateRequest,
    HospitalRead,
    MeResponse,
    OrganizationCreateRequest,
    PlanCreateRequest,
    PlanUpdateRequest,
    ProviderRead,
    RegisterRequest,
    UserCreateRequest,
)
from backend.services import admin as admin_service

router = APIRouter(tags=["admin"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AccessDeniedError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, admin_service.AdminServiceError):
        code = status.HTTP_400_BAD_REQUEST
        if "not found" in str(exc).lower():
            code = status.HTTP_404_NOT_FOUND
        return HTTPException(status_code=code, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(setting_limit("rate_limit_register"))
async def register(
    request: Request, body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    try:
        user = await admin_service.register_tenant(db, body)
    except Exception as exc:
        raise _http_error(exc) from exc
    access_token = create_access_token(user.id, user.role, user.organization_id)
    refresh_token = await issue_refresh_token(db, user.id)
    set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token)


@router.get("/auth/me", response_model=MeResponse)
async def me(
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> MeResponse:
    try:
        return await admin_service.get_me(db, ctx)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/employers/me", response_model=EmployerRead)
async def employer_me(
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> EmployerRead:
    try:
        employer = await admin_service.get_employer_me(db, ctx)
    except Exception as exc:
        raise _http_error(exc) from exc
    return EmployerRead.model_validate(employer)


@router.patch("/employers/me", response_model=EmployerRead)
async def patch_employer_me(
    body: EmployerUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> EmployerRead:
    try:
        employer = await admin_service.update_employer_me(db, ctx, body)
    except Exception as exc:
        raise _http_error(exc) from exc
    return EmployerRead.model_validate(employer)


@router.get("/providers/me", response_model=ProviderRead)
async def provider_me(
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> ProviderRead:
    try:
        provider = await admin_service.get_provider_me(db, ctx)
    except Exception as exc:
        raise _http_error(exc) from exc
    return ProviderRead(
        id=provider.id,
        organization_id=provider.organization_id,
        name=provider.name,
        hospital_count=len(provider.hospitals or []),
    )


@router.post(
    "/providers/me/hospitals",
    response_model=HospitalRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_hospital(
    body: HospitalCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> HospitalRead:
    try:
        hospital = await admin_service.add_hospital(db, ctx, body)
    except Exception as exc:
        raise _http_error(exc) from exc
    return HospitalRead.model_validate(hospital)


@router.post("/plans", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
async def create_plan(
    body: PlanCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> PlanRead:
    try:
        return await admin_service.create_plan(db, ctx, body)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.patch("/plans/{plan_id}", response_model=PlanRead)
async def patch_plan(
    plan_id: UUID,
    body: PlanUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> PlanRead:
    try:
        return await admin_service.update_plan(db, ctx, plan_id, body)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post(
    "/plans/{plan_id}/versions",
    response_model=PlanVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan_version(
    plan_id: UUID,
    body: PlanVersionCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> PlanVersionRead:
    try:
        version = await admin_service.create_plan_version(db, ctx, plan_id, body)
    except Exception as exc:
        raise _http_error(exc) from exc
    return PlanVersionRead.model_validate(version)


@router.get("/plans/{plan_id}/versions", response_model=list[PlanVersionRead])
async def list_plan_versions(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> list[PlanVersionRead]:
    try:
        versions = await admin_service.list_plan_versions(db, ctx, plan_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return [PlanVersionRead.model_validate(version) for version in versions]


@router.patch("/plan-versions/{version_id}/review", response_model=PlanVersionRead)
async def review_plan_version(
    version_id: UUID,
    body: PlanVersionReviewRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> PlanVersionRead:
    try:
        version = await admin_service.review_plan_version(db, ctx, version_id, body)
    except Exception as exc:
        raise _http_error(exc) from exc
    return PlanVersionRead.model_validate(version)


@router.get("/organizations", response_model=list[OrganizationRead])
async def list_orgs(
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> list[OrganizationRead]:
    try:
        orgs = await admin_service.list_organizations(db, ctx)
    except Exception as exc:
        raise _http_error(exc) from exc
    return [OrganizationRead.model_validate(item) for item in orgs]


@router.post("/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_org(
    body: OrganizationCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> OrganizationRead:
    try:
        org = await admin_service.create_organization(db, ctx, body)
    except Exception as exc:
        raise _http_error(exc) from exc
    return OrganizationRead.model_validate(org)


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_security_context),
) -> UserRead:
    try:
        user = await admin_service.create_user(db, ctx, body)
    except Exception as exc:
        raise _http_error(exc) from exc
    return UserRead.model_validate(user)
