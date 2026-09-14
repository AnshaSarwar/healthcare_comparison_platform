import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.policies import SecurityContext
from backend.domain.enums import UserRole
from backend.models import RefreshToken, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: UUID, role: UserRole, organization_id: UUID) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "org_id": str(organization_id),
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def issue_refresh_token(session: AsyncSession, user_id: UUID) -> str:
    raw = generate_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw),
            expires_at=expires_at,
        )
    )
    await session.commit()
    return raw


async def rotate_refresh_token(
    session: AsyncSession, raw_token: str
) -> tuple[str, User] | None:
    token_hash = hash_refresh_token(raw_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        return None

    now = datetime.now(UTC)
    if existing.revoked_at is not None or existing.expires_at < now:
        # Reuse of an already-rotated/expired token: treat as compromised and
        # revoke every other active token for this user.
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == existing.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await session.commit()
        return None

    result = await session.execute(select(User).where(User.id == existing.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return None

    new_raw = generate_refresh_token()
    new_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(new_raw),
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    session.add(new_token)
    await session.flush()

    existing.revoked_at = now
    existing.replaced_by_id = new_token.id
    await session.commit()
    return new_raw, user


async def revoke_refresh_token(session: AsyncSession, raw_token: str) -> None:
    token_hash = hash_refresh_token(raw_token)
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()


def decode_access_token(token: str) -> SecurityContext:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return SecurityContext(
            user_id=UUID(payload["sub"]),
            role=UserRole(payload["role"]),
            organization_id=UUID(payload["org_id"]),
        )
    except (JWTError, KeyError, ValueError) as exc:
        raise ValueError("Invalid token") from exc


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user
