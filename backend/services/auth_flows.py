"""Email verification, password reset, and invite-based provider onboarding.

Split out from `backend/services/admin.py` since these are a distinct bounded concern
(token issuance/consumption + outbound email) rather than tenant CRUD. See "Auth" and
"Known gaps" in CLAUDE.md.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.email import EmailMessage, send_email
from backend.core.policies import AccessDeniedError, SecurityContext, is_platform_admin
from backend.core.security import generate_secure_token, hash_password, hash_secure_token
from backend.domain.enums import OrganizationType, UserRole
from backend.models import (
    EmailVerificationToken,
    HealthcareProvider,
    Organization,
    PasswordResetToken,
    ProviderInvite,
    RefreshToken,
    User,
)
from backend.schemas.auth import (
    ProviderInviteCreateRequest,
    ProviderInvitePreview,
    ProviderInviteRead,
)

settings = get_settings()


class AuthFlowError(Exception):
    pass


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


async def send_verification_email(session: AsyncSession, user: User) -> None:
    raw = generate_secure_token()
    expires_at = datetime.now(UTC) + timedelta(hours=settings.email_verification_token_expire_hours)
    session.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_secure_token(raw),
            expires_at=expires_at,
        )
    )
    await session.commit()
    link = f"{settings.frontend_base_url}/verify-email?token={raw}"
    await send_email(
        EmailMessage(
            to=user.email,
            subject="Verify your Benefits Compare email",
            body=(
                f"Confirm your email address to finish setting up your account:\n\n{link}\n\n"
                f"This link expires in {settings.email_verification_token_expire_hours} hours."
            ),
        )
    )


async def resend_verification_email(session: AsyncSession, email: str) -> None:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or user.email_verified:
        return  # Don't reveal whether the address is registered or already verified.
    await send_verification_email(session, user)


async def confirm_email_verification(session: AsyncSession, raw_token: str) -> User:
    token_hash = hash_secure_token(raw_token)
    result = await session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
    )
    token = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if token is None or token.used_at is not None or token.expires_at < now:
        raise AuthFlowError("Invalid or expired verification token")
    user = await session.get(User, token.user_id)
    if user is None:
        raise AuthFlowError("Invalid or expired verification token")
    user.email_verified = True
    token.used_at = now
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


async def request_password_reset(session: AsyncSession, email: str) -> None:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return  # Don't reveal whether the address is registered.

    raw = generate_secure_token()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.password_reset_token_expire_minutes)
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_secure_token(raw),
            expires_at=expires_at,
        )
    )
    await session.commit()
    link = f"{settings.frontend_base_url}/reset-password?token={raw}"
    await send_email(
        EmailMessage(
            to=user.email,
            subject="Reset your Benefits Compare password",
            body=(
                f"Reset your password:\n\n{link}\n\n"
                f"This link expires in {settings.password_reset_token_expire_minutes} minutes. "
                "If you didn't request this, you can ignore this email."
            ),
        )
    )


async def confirm_password_reset(session: AsyncSession, raw_token: str, new_password: str) -> User:
    token_hash = hash_secure_token(raw_token)
    result = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    token = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if token is None or token.used_at is not None or token.expires_at < now:
        raise AuthFlowError("Invalid or expired reset token")
    user = await session.get(User, token.user_id)
    if user is None:
        raise AuthFlowError("Invalid or expired reset token")

    user.hashed_password = hash_password(new_password)
    token.used_at = now
    # A password reset is a compromise-recovery action: kill every existing session.
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Provider invites (invite-based provider onboarding)
# ---------------------------------------------------------------------------


def _invite_status(invite: ProviderInvite, now: datetime) -> str:
    if invite.accepted_at is not None:
        return "accepted"
    if invite.revoked_at is not None:
        return "revoked"
    if invite.expires_at < now:
        return "expired"
    return "pending"


async def create_provider_invite(
    session: AsyncSession, ctx: SecurityContext, body: ProviderInviteCreateRequest
) -> ProviderInvite:
    if not is_platform_admin(ctx):
        raise AccessDeniedError("Platform admin only")
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise AuthFlowError("Email already registered")

    raw = generate_secure_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.provider_invite_token_expire_days)
    invite = ProviderInvite(
        id=uuid4(),
        email=body.email,
        organization_name=body.organization_name,
        profile_name=body.profile_name,
        invited_by_user_id=ctx.user_id,
        token_hash=hash_secure_token(raw),
        expires_at=expires_at,
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    link = f"{settings.frontend_base_url}/accept-invite?token={raw}"
    await send_email(
        EmailMessage(
            to=body.email,
            subject="You're invited to Benefits Compare",
            body=(
                f"You've been invited to onboard {body.organization_name} as a healthcare "
                f"provider on Benefits Compare:\n\n{link}\n\n"
                f"This link expires in {settings.provider_invite_token_expire_days} days."
            ),
        )
    )
    return invite


async def list_provider_invites(session: AsyncSession, ctx: SecurityContext) -> list[ProviderInviteRead]:
    if not is_platform_admin(ctx):
        raise AccessDeniedError("Platform admin only")
    result = await session.execute(select(ProviderInvite).order_by(ProviderInvite.created_at.desc()))
    invites = result.scalars().all()
    now = datetime.now(UTC)
    return [
        ProviderInviteRead(
            id=invite.id,
            email=invite.email,
            organization_name=invite.organization_name,
            profile_name=invite.profile_name,
            status=_invite_status(invite, now),
            created_at=invite.created_at,
            expires_at=invite.expires_at,
            accepted_at=invite.accepted_at,
        )
        for invite in invites
    ]


async def revoke_provider_invite(session: AsyncSession, ctx: SecurityContext, invite_id: UUID) -> None:
    if not is_platform_admin(ctx):
        raise AccessDeniedError("Platform admin only")
    invite = await session.get(ProviderInvite, invite_id)
    if invite is None:
        raise AuthFlowError("Invite not found")
    if invite.accepted_at is not None:
        raise AuthFlowError("Invite already accepted")
    invite.revoked_at = datetime.now(UTC)
    await session.commit()


async def _get_valid_invite_by_token(session: AsyncSession, raw_token: str) -> ProviderInvite:
    token_hash = hash_secure_token(raw_token)
    result = await session.execute(
        select(ProviderInvite).where(ProviderInvite.token_hash == token_hash)
    )
    invite = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if (
        invite is None
        or invite.accepted_at is not None
        or invite.revoked_at is not None
        or invite.expires_at < now
    ):
        raise AuthFlowError("Invalid or expired invite")
    return invite


async def preview_provider_invite(session: AsyncSession, raw_token: str) -> ProviderInvitePreview:
    invite = await _get_valid_invite_by_token(session, raw_token)
    return ProviderInvitePreview(
        email=invite.email,
        organization_name=invite.organization_name,
        profile_name=invite.profile_name,
        expires_at=invite.expires_at,
    )


async def accept_provider_invite(session: AsyncSession, raw_token: str, password: str) -> User:
    invite = await _get_valid_invite_by_token(session, raw_token)

    org = Organization(
        id=uuid4(), name=invite.organization_name, org_type=OrganizationType.HEALTHCARE_PROVIDER
    )
    session.add(org)
    await session.flush()
    session.add(HealthcareProvider(id=uuid4(), organization_id=org.id, name=invite.profile_name))

    user = User(
        id=uuid4(),
        email=invite.email,
        hashed_password=hash_password(password),
        role=UserRole.HEALTHCARE_ORG_ADMIN,
        organization_id=org.id,
        # A platform admin already vetted this org before sending the invite.
        email_verified=True,
    )
    session.add(user)

    invite.accepted_at = datetime.now(UTC)
    invite.created_organization_id = org.id
    await session.commit()
    await session.refresh(user)
    return user
