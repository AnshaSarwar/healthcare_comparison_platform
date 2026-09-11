"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-08

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

organizationtype = sa.Enum("employer", "healthcare_provider", name="organizationtype")
userrole = sa.Enum("platform_admin", "employer_admin", "healthcare_org_admin", name="userrole")
coveragetype = sa.Enum("opd", "ipd", "opd_ipd", name="coveragetype")
documentindexstatus = sa.Enum("pending", "indexed", "failed", name="documentindexstatus")
comparisonrequeststatus = sa.Enum(
    "pending", "processing", "completed", "failed", name="comparisonrequeststatus"
)


def upgrade() -> None:
    organizationtype.create(op.get_bind(), checkfirst=True)
    userrole.create(op.get_bind(), checkfirst=True)
    coveragetype.create(op.get_bind(), checkfirst=True)
    documentindexstatus.create(op.get_bind(), checkfirst=True)
    comparisonrequeststatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("org_type", organizationtype, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", userrole, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "employers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("demographics", sa.JSON(), nullable=False),
        sa.Column("requirements", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "healthcare_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "hospitals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healthcare_providers.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("city", sa.String(128), nullable=False),
        sa.Column("tier", sa.String(64)),
    )
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("healthcare_providers.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("coverage_type", coveragetype, nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False),
        sa.Column("pricing_tiers", sa.JSON(), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "plan_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", documentindexstatus),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_foreign_key(
        "fk_plans_source_document_id",
        "plans",
        "plan_documents",
        ["source_document_id"],
        ["id"],
    )
    op.create_table(
        "comparison_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employers.id"), nullable=False),
        sa.Column("plan_ids", sa.JSON(), nullable=False),
        sa.Column("status", comparisonrequeststatus),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "comparison_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "comparison_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comparison_requests.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("eligibility_matrix", sa.JSON(), nullable=False),
        sa.Column("scored_ranking", sa.JSON(), nullable=False),
        sa.Column("narrative_explanation", sa.Text(), nullable=True),
        sa.Column("audit_trace", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("comparison_results")
    op.drop_table("comparison_requests")
    op.drop_constraint("fk_plans_source_document_id", "plans", type_="foreignkey")
    op.drop_table("plan_documents")
    op.drop_table("plans")
    op.drop_table("hospitals")
    op.drop_table("healthcare_providers")
    op.drop_table("employers")
    op.drop_table("users")
    op.drop_table("organizations")
    comparisonrequeststatus.drop(op.get_bind(), checkfirst=True)
    documentindexstatus.drop(op.get_bind(), checkfirst=True)
    coveragetype.drop(op.get_bind(), checkfirst=True)
    userrole.drop(op.get_bind(), checkfirst=True)
    organizationtype.drop(op.get_bind(), checkfirst=True)
