from collections.abc import AsyncGenerator

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.policies import SecurityContext
from backend.core.security import decode_access_token
from backend.db.session import get_db as _get_db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in _get_db():
        yield session


def get_security_context(request: Request) -> SecurityContext:
    token: str | None = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[len("bearer ") :].strip()
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        ctx = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    # Side effect for backend.core.rate_limit.user_or_ip_key: dependency
    # resolution always completes before the endpoint (and slowapi's
    # rate-limit check on it) runs, so this is reliably set in time.
    request.state.rate_limit_user_id = str(ctx.user_id)
    return ctx
