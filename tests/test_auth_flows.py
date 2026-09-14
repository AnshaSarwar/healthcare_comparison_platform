"""Email verification, password reset, and invite-based provider onboarding.

Mirrors the rest of the suite (see tests/test_rate_limit.py, tests/test_api_integration.py):
no live Postgres/Redis in CI, so these stick to pure logic (token helpers, the invite
status derivation, and guard clauses that raise before touching the DB session) plus
auth-shape checks on the new endpoints via dependency overrides.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.v1.router import api_router
from backend.core.policies import AccessDeniedError, SecurityContext
from backend.core.security import generate_secure_token, hash_secure_token
from backend.domain.enums import OrganizationType, UserRole
from backend.models import ProviderInvite
from backend.schemas.admin import RegisterRequest
from backend.schemas.auth import (
    PasswordResetConfirmRequest,
    ProviderInviteAcceptRequest,
    ProviderInviteCreateRequest,
    VerifyEmailRequest,
)
from backend.services import admin as admin_service
from backend.services import auth_flows


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    with TestClient(app) as test_client:
        yield test_client


def _employer_ctx() -> SecurityContext:
    return SecurityContext(user_id=uuid4(), role=UserRole.EMPLOYER_ADMIN, organization_id=uuid4())


def _provider_invite(**overrides) -> ProviderInvite:
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        email="new-provider@example.com",
        organization_name="New Provider Org",
        profile_name="New Provider",
        invited_by_user_id=uuid4(),
        token_hash="unused",
        created_at=now,
        expires_at=now + timedelta(days=7),
        accepted_at=None,
        revoked_at=None,
    )
    defaults.update(overrides)
    return ProviderInvite(**defaults)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def test_generate_secure_token_is_unique_and_url_safe() -> None:
    tokens = {generate_secure_token() for _ in range(20)}
    assert len(tokens) == 20
    for token in tokens:
        assert len(token) > 32


def test_hash_secure_token_is_deterministic_and_not_reversible() -> None:
    raw = generate_secure_token()
    assert hash_secure_token(raw) == hash_secure_token(raw)
    assert hash_secure_token(raw) != raw
    assert hash_secure_token(raw) != hash_secure_token(generate_secure_token())


# ---------------------------------------------------------------------------
# Invite status derivation (pure)
# ---------------------------------------------------------------------------


def test_invite_status_pending_by_default() -> None:
    now = datetime.now(UTC)
    invite = _provider_invite()
    assert auth_flows._invite_status(invite, now) == "pending"


def test_invite_status_accepted_takes_priority() -> None:
    now = datetime.now(UTC)
    invite = _provider_invite(accepted_at=now, revoked_at=now)
    assert auth_flows._invite_status(invite, now) == "accepted"


def test_invite_status_revoked() -> None:
    now = datetime.now(UTC)
    invite = _provider_invite(revoked_at=now)
    assert auth_flows._invite_status(invite, now) == "revoked"


def test_invite_status_expired() -> None:
    now = datetime.now(UTC)
    invite = _provider_invite(expires_at=now - timedelta(minutes=1))
    assert auth_flows._invite_status(invite, now) == "expired"


# ---------------------------------------------------------------------------
# Guard clauses that must raise before touching the DB session
# ---------------------------------------------------------------------------


async def test_register_tenant_rejects_healthcare_provider_self_registration() -> None:
    body = RegisterRequest(
        email="provider@example.com",
        password="password123",
        organization_name="Some Provider",
        org_type=OrganizationType.HEALTHCARE_PROVIDER,
        profile_name="Some Provider",
    )
    with pytest.raises(admin_service.AdminServiceError, match="invite"):
        await admin_service.register_tenant(None, body)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "coro_factory",
    [
        lambda ctx: auth_flows.create_provider_invite(
            None,
            ctx,
            ProviderInviteCreateRequest(
                email="p@example.com", organization_name="Org", profile_name="Org"
            ),
        ),
        lambda ctx: auth_flows.list_provider_invites(None, ctx),
        lambda ctx: auth_flows.revoke_provider_invite(None, ctx, uuid4()),
    ],
)
async def test_invite_management_requires_platform_admin(coro_factory) -> None:
    with pytest.raises(AccessDeniedError):
        await coro_factory(_employer_ctx())


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_verify_email_request_requires_token() -> None:
    with pytest.raises(ValidationError):
        VerifyEmailRequest()  # type: ignore[call-arg]
    assert VerifyEmailRequest(token="abc").token == "abc"


def test_password_reset_confirm_enforces_min_password_length() -> None:
    with pytest.raises(ValidationError):
        PasswordResetConfirmRequest(token="abc", new_password="short")
    assert PasswordResetConfirmRequest(token="abc", new_password="longenough").new_password == (
        "longenough"
    )


def test_provider_invite_accept_enforces_min_password_length() -> None:
    with pytest.raises(ValidationError):
        ProviderInviteAcceptRequest(password="short")


def test_provider_invite_create_request_validates_email() -> None:
    with pytest.raises(ValidationError):
        ProviderInviteCreateRequest(
            email="not-an-email", organization_name="Org", profile_name="Org"
        )


# ---------------------------------------------------------------------------
# Endpoint auth shape (no DB touched: auth dependency rejects before the handler runs)
# ---------------------------------------------------------------------------


def test_create_invite_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/v1/invites",
        json={"email": "p@example.com", "organization_name": "Org", "profile_name": "Org"},
    )
    assert response.status_code == 401


def test_list_invites_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/invites")
    assert response.status_code == 401


def test_revoke_invite_requires_auth(client: TestClient) -> None:
    response = client.post(f"/api/v1/invites/{uuid4()}/revoke")
    assert response.status_code == 401
