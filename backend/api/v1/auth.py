from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.core.config import get_settings
from backend.core.rate_limit import limiter, setting_limit
from backend.core.security import (
    authenticate_user,
    create_access_token,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)
from backend.schemas import (
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ProviderInviteAcceptRequest,
    ProviderInvitePreview,
    ResendVerificationRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from backend.services import auth_flows

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

REFRESH_COOKIE_PATH = f"{settings.api_v1_prefix}/auth"
ACCESS_TOKEN_MAX_AGE = settings.access_token_expire_minutes * 60
REFRESH_TOKEN_MAX_AGE = settings.refresh_token_expire_days * 24 * 60 * 60


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=ACCESS_TOKEN_MAX_AGE,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=REFRESH_TOKEN_MAX_AGE,
        path=REFRESH_COOKIE_PATH,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path=REFRESH_COOKIE_PATH)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(setting_limit("rate_limit_login"))
async def login(
    request: Request, body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    user = await authenticate_user(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user.id, user.role, user.organization_id)
    refresh_token = await issue_refresh_token(db, user.id)
    set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(setting_limit("rate_limit_refresh"))
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    raw_refresh_token = request.cookies.get("refresh_token")
    if not raw_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    rotated = await rotate_refresh_token(db, raw_refresh_token)
    if rotated is None:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    new_refresh_token, user = rotated
    access_token = create_access_token(user.id, user.role, user.organization_id)
    set_auth_cookies(response, access_token, new_refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(setting_limit("rate_limit_logout"))
async def logout(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> None:
    raw_refresh_token = request.cookies.get("refresh_token")
    if raw_refresh_token:
        await revoke_refresh_token(db, raw_refresh_token)
    clear_auth_cookies(response)


@router.post("/email/verify", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(setting_limit("rate_limit_verify_email"))
async def verify_email(
    request: Request,
    body: VerifyEmailRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    # `response` is unused in the body but required: slowapi's headers_enabled=True
    # injects rate-limit headers into it and raises if no Response param is declared
    # (see the ordering note in backend/core/rate_limit.py).
    try:
        await auth_flows.confirm_email_verification(db, body.token)
    except auth_flows.AuthFlowError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/email/resend-verification", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(setting_limit("rate_limit_resend_verification"))
async def resend_verification(
    request: Request,
    body: ResendVerificationRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    # Always 202, regardless of whether the address is registered/already verified.
    await auth_flows.resend_verification_email(db, body.email)


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(setting_limit("rate_limit_password_reset_request"))
async def request_password_reset(
    request: Request,
    body: PasswordResetRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    # Always 202, regardless of whether the address is registered.
    await auth_flows.request_password_reset(db, body.email)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(setting_limit("rate_limit_password_reset_confirm"))
async def confirm_password_reset(
    request: Request,
    body: PasswordResetConfirmRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await auth_flows.confirm_password_reset(db, body.token, body.new_password)
    except auth_flows.AuthFlowError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/invites/{token}", response_model=ProviderInvitePreview)
@limiter.limit(setting_limit("rate_limit_invite_accept"))
async def preview_invite(
    request: Request, token: str, response: Response, db: AsyncSession = Depends(get_db)
) -> ProviderInvitePreview:
    try:
        return await auth_flows.preview_provider_invite(db, token)
    except auth_flows.AuthFlowError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/invites/{token}/accept", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(setting_limit("rate_limit_invite_accept"))
async def accept_invite(
    request: Request,
    token: str,
    body: ProviderInviteAcceptRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        user = await auth_flows.accept_provider_invite(db, token, body.password)
    except auth_flows.AuthFlowError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    access_token = create_access_token(user.id, user.role, user.organization_id)
    refresh_token = await issue_refresh_token(db, user.id)
    set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token)
