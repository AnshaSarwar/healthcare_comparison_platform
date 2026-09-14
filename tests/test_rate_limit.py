"""Tests for backend.core.rate_limit.

These exercise the limiter logic in isolation, using a fresh `Limiter`
instance backed by the `limits` package's in-memory storage (`memory://`)
rather than a live Redis instance -- no real infra required to run this
file. It builds its own tiny FastAPI app (separate from `backend.main.app`
and from `backend.core.rate_limit.limiter`, which is wired to Redis) so it
never touches network/Redis and can't bleed rate-limit state into other
tests.

What this does NOT verify (needs real Redis, see manual verification steps
in the task report): that `backend.core.rate_limit.limiter`'s Redis-backed
storage actually round-trips INCR/EXPIRE against a live Redis server, and
that limiter state is shared across multiple app instances/processes.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.core.rate_limit import setting_limit, user_or_ip_key


def _build_app(limiter: Limiter, key_func=None) -> FastAPI:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    limit_decorator = limiter.limit("2/minute", key_func=key_func) if key_func else limiter.limit(
        "2/minute"
    )

    @app.get("/ping")
    @limit_decorator
    async def ping(request: Request, response: Response) -> dict[str, str]:
        # Mirrors the production routes: none of the 6 rate-limited endpoints
        # in backend/api/v1/{auth,admin,rag,agents}.py return a bare dict --
        # they either return a Response subclass directly (rag_query,
        # agent_chat -> StreamingResponse) or declare a `response: Response`
        # parameter slowapi can inject rate-limit headers into (login,
        # refresh, logout, register). A route with neither would make
        # headers_enabled=True raise inside slowapi.
        return {"status": "ok"}

    return app


def test_limiter_blocks_after_threshold_with_memory_storage() -> None:
    """Hammer a 2/minute route 3 times; the 3rd call should get a 429."""
    limiter = Limiter(key_func=lambda request: "fixed-key", storage_uri="memory://")
    app = _build_app(limiter)

    with TestClient(app) as client:
        first = client.get("/ping")
        second = client.get("/ping")
        third = client.get("/ping")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert "Rate limit exceeded" in third.json()["error"]
    # headers_enabled defaults to False on this ad-hoc Limiter, so we don't
    # assert on Retry-After here -- see the headers-enabled test below.


def test_limiter_emits_retry_after_header_when_headers_enabled() -> None:
    limiter = Limiter(
        key_func=lambda request: "fixed-key-2",
        storage_uri="memory://",
        headers_enabled=True,
    )
    app = _build_app(limiter)

    with TestClient(app) as client:
        client.get("/ping")
        client.get("/ping")
        blocked = client.get("/ping")

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert int(blocked.headers["Retry-After"]) >= 0


def test_limiter_keys_are_independent_per_client() -> None:
    """Different keys (e.g. different users/IPs) get independent buckets."""
    counter = {"n": 0}

    def alternating_key(request: Request) -> str:
        counter["n"] += 1
        # Every other request looks like a different client.
        return f"client-{counter['n'] % 2}"

    limiter = Limiter(key_func=alternating_key, storage_uri="memory://")
    app = _build_app(limiter)

    with TestClient(app) as client:
        responses = [client.get("/ping") for _ in range(4)]

    # 4 requests split across 2 independent keys, limit 2/minute each ->
    # none of them should be blocked.
    assert all(r.status_code == 200 for r in responses)


def test_user_or_ip_key_prefers_authenticated_user_id() -> None:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [],
        "client": ("203.0.113.5", 12345),
    }
    request = Request(scope)
    request.state.rate_limit_user_id = "user-123"

    assert user_or_ip_key(request) == "user:user-123"


def test_user_or_ip_key_falls_back_to_ip_when_unauthenticated() -> None:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [],
        "client": ("203.0.113.5", 12345),
    }
    request = Request(scope)
    # No rate_limit_user_id set on request.state -- simulates an
    # unauthenticated caller (e.g. /auth/login, /auth/register).

    assert user_or_ip_key(request) == "ip:203.0.113.5"


def test_setting_limit_reads_live_settings_value(monkeypatch) -> None:
    """`setting_limit` must re-read Settings each call, not freeze at import."""
    from backend.core.config import get_settings

    settings = get_settings()
    original = settings.rate_limit_login
    try:
        get_fn = setting_limit("rate_limit_login")
        assert get_fn() == original

        monkeypatch.setattr(settings, "rate_limit_login", "1/second")
        assert get_fn() == "1/second"
    finally:
        monkeypatch.setattr(settings, "rate_limit_login", original)
