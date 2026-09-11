"""add plan version import provenance fields

Revision ID: 0005_import_provenance
Revises: 0004_human_review_audit
Create Date: 2026-09-11

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_import_provenance"
down_revision: Union[str, Sequence[str], None] = "0004_human_review_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plan_versions",
        sa.Column("imported_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "plan_versions",
        sa.Column("imported_by_org_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "plan_versions",
        sa.Column("imported_by_role", sa.Enum(name="userrole", create_type=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_plan_versions_imported_by_user",
        "plan_versions",
        "users",
        ["imported_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_plan_versions_imported_by_org",
        "plan_versions",
        "organizations",
        ["imported_by_org_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_plan_versions_imported_by_org", "plan_versions", type_="foreignkey")
    op.drop_constraint("fk_plan_versions_imported_by_user", "plan_versions", type_="foreignkey")
    op.drop_column("plan_versions", "imported_by_role")
    op.drop_column("plan_versions", "imported_by_org_id")
    op.drop_column("plan_versions", "imported_by_user_id")
