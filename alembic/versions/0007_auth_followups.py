"""email verification, password reset, and provider-invite tables

Revision ID: 0007_auth_followups
Revises: 0006_refresh_tokens
Create Date: 2026-09-14

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_auth_followups"
down_revision: Union[str, Sequence[str], None] = "0006_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("users", "email_verified", server_default=None)

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_email_verification_tokens_user_id",
        "email_verification_tokens",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_index(
        "ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"]
    )
    op.create_index(
        "ix_email_verification_tokens_token_hash",
        "email_verification_tokens",
        ["token_hash"],
        unique=True,
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_password_reset_tokens_user_id",
        "password_reset_tokens",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index(
        "ix_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
    )

    op.create_table(
        "provider_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("organization_name", sa.String(length=255), nullable=False),
        sa.Column("profile_name", sa.String(length=255), nullable=False),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_provider_invites_invited_by_user_id",
        "provider_invites",
        "users",
        ["invited_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_provider_invites_created_organization_id",
        "provider_invites",
        "organizations",
        ["created_organization_id"],
        ["id"],
    )
    op.create_index("ix_provider_invites_email", "provider_invites", ["email"])
    op.create_index(
        "ix_provider_invites_token_hash", "provider_invites", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_provider_invites_token_hash", table_name="provider_invites")
    op.drop_index("ix_provider_invites_email", table_name="provider_invites")
    op.drop_constraint(
        "fk_provider_invites_created_organization_id", "provider_invites", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_provider_invites_invited_by_user_id", "provider_invites", type_="foreignkey"
    )
    op.drop_table("provider_invites")

    op.drop_index("ix_password_reset_tokens_token_hash", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_constraint(
        "fk_password_reset_tokens_user_id", "password_reset_tokens", type_="foreignkey"
    )
    op.drop_table("password_reset_tokens")

    op.drop_index(
        "ix_email_verification_tokens_token_hash", table_name="email_verification_tokens"
    )
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_constraint(
        "fk_email_verification_tokens_user_id", "email_verification_tokens", type_="foreignkey"
    )
    op.drop_table("email_verification_tokens")

    op.drop_column("users", "email_verified")
