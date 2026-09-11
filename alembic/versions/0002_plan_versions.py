"""add versioned policy records

Revision ID: 0002_plan_versions
Revises: 0001_initial
Create Date: 2026-09-10

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_plan_versions"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

policyreviewstatus = sa.Enum(
    "draft",
    "needs_review",
    "approved",
    "archived",
    name="policyreviewstatus",
)
coveragetype = sa.Enum("opd", "ipd", "opd_ipd", name="coveragetype")


def upgrade() -> None:
    policyreviewstatus.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "plan_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id"),
            nullable=False,
        ),
        sa.Column("version_label", sa.String(128), nullable=False),
        sa.Column("coverage_type", coveragetype, nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_status", policyreviewstatus, nullable=False),
        sa.Column("raw_terms", sa.JSON(), nullable=False),
        sa.Column("normalized_terms", sa.JSON(), nullable=False),
        sa.Column("pricing_tiers", sa.JSON(), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plan_documents.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("plan_versions")
    policyreviewstatus.drop(op.get_bind(), checkfirst=True)
