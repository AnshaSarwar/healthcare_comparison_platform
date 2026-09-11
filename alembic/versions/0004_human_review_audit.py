"""add human review audit fields

Revision ID: 0004_human_review_audit
Revises: 0003_extraction_metadata
Create Date: 2026-09-10

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_human_review_audit"
down_revision: Union[str, Sequence[str], None] = "0003_extraction_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE policyreviewstatus ADD VALUE IF NOT EXISTS 'needs_correction'")
    op.execute("ALTER TYPE policyreviewstatus ADD VALUE IF NOT EXISTS 'rejected'")
    op.add_column(
        "plan_versions",
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "plan_versions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("plan_versions", sa.Column("review_notes", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_plan_versions_reviewed_by",
        "plan_versions",
        "users",
        ["reviewed_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_plan_versions_reviewed_by", "plan_versions", type_="foreignkey")
    op.drop_column("plan_versions", "review_notes")
    op.drop_column("plan_versions", "reviewed_at")
    op.drop_column("plan_versions", "reviewed_by")
