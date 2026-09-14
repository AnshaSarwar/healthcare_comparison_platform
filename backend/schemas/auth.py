from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class ProviderInviteCreateRequest(BaseModel):
    email: EmailStr
    organization_name: str = Field(min_length=1, max_length=255)
    profile_name: str = Field(min_length=1, max_length=255)


class ProviderInvitePreview(BaseModel):
    """Public shape returned when looking up an invite by its raw token."""

    email: str
    organization_name: str
    profile_name: str
    expires_at: datetime


class ProviderInviteAcceptRequest(BaseModel):
    password: str = Field(min_length=8)


class ProviderInviteRead(BaseModel):
    id: UUID
    email: str
    organization_name: str
    profile_name: str
    status: str
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None

    model_config = {"from_attributes": True}
