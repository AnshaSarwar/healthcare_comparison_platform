"""Rate limiting for the most abuse-prone/expensive routes in the app.

Built on `slowapi` (a thin FastAPI/Starlette wrapper around the `limits`
package) with a Redis storage backend, since this app already depends on
Redis and needs a limiter that is shared across instances rather than
in-memory-per-process. The Redis URL is sourced from the same
`Settings.redis_url` used by `backend/rag/cache.py`'s `get_redis()`, so both
point at the same Redis deployment.

Usage in a route module::

    from fastapi import Request
    from backend.core.rate_limit import limiter, setting_limit, user_or_ip_key

    @router.post("/login")
    @limiter.limit(setting_limit("rate_limit_login"))
    async def login(request: Request, ...): ...

    @router.post("/rag/query")
    @limiter.limit(setting_limit("rate_limit_rag_query"), key_func=user_or_ip_key)
    async def rag_query(request: Request, ..., ctx=Depends(get_security_context)): ...

Notes on ordering:
- `@router.post(...)` must be the outermost decorator; `@limiter.limit(...)`
  goes directly on the endpoint function (slowapi's documented pattern).
- The decorated endpoint function MUST declare a `request: Request`
  parameter (slowapi inspects the signature for it), even if the function
  body never uses it directly.
- slowapi's decorator calls the limiter's own `.hit()` using the `Limiter`
  instance closed over by the decorator (this module's `limiter`) -- it does
  NOT depend on `request.app.state.limiter` being set. Only the *exception
  handler* wired up in `backend/main.py` needs `app.state.limiter`. This
  means the limiter is fully active even against a bare `FastAPI()` test app
  that never calls `backend.main`'s app-construction code (see
  `tests/test_api_integration.py`); the only thing such a test app misses is
  slowapi's polished 429 JSON body -- FastAPI's default `HTTPException`
  handler still returns a plain 429 with `{"detail": ...}` because
  `RateLimitExceeded` is itself an `HTTPException` subclass.

Per-user vs per-IP keys:
- Unauthenticated routes (`/auth/login`, `/auth/register`) are keyed by
  client IP (`request.client.host`, via slowapi's `get_remote_address`).
  This app has no reverse-proxy header trust configured, so we deliberately
  do NOT read `X-Forwarded-For` -- that requires separate proxy-trust
  configuration this app doesn't have.
- Authenticated routes (`/rag/query`, `/agents/chat`) are keyed by
  authenticated user id via `user_or_ip_key`, which reads
  `request.state.rate_limit_user_id`. That attribute is set as a side
  effect inside `get_security_context` (`backend/api/deps.py`) during
  FastAPI's dependency resolution, which always completes *before* the
  wrapped endpoint (and therefore slowapi's rate-limit check) runs -- so the
  value is reliably present by the time the key function is called. Falls
  back to IP if, for some reason, it isn't set.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.config import get_settings


def user_or_ip_key(request: Request) -> str:
    """Rate-limit key: authenticated user id if present, else client IP."""
    user_id = getattr(request.state, "rate_limit_user_id", None)
    if user_id:
        return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


def setting_limit(setting_name: str) -> Callable[[], str]:
    """Return a zero-arg callable yielding a `Settings` field's current value.

    Passed as the `limit_value` to `@limiter.limit(...)` so the limit string
    (e.g. "5/minute") stays configurable via `.env`/`Settings` rather than
    hardcoded in route files, while still being re-read live (not frozen at
    import time) since `get_settings()` returns the cached singleton.
    """

    def _get() -> str:
        return getattr(get_settings(), setting_name)

    _get.__name__ = f"setting_limit_{setting_name}"
    return _get


_settings = get_settings()

# A single shared Limiter instance, used both as the decorator factory in
# route modules and as the app-level limiter registered in backend/main.py.
# Default key_func (get_remote_address / per-IP) applies to any route that
# doesn't pass its own `key_func=` override.
#
# in_memory_fallback_enabled + swallow_errors: if Redis is unreachable, don't
# take down the whole app -- fall back to a per-process in-memory limiter
# (weaker guarantee, but keeps the service and its test suite usable) rather
# than raising on every request.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_settings.redis_url,
    strategy="fixed-window",
    headers_enabled=True,
    swallow_errors=True,
    in_memory_fallback_enabled=True,
)
