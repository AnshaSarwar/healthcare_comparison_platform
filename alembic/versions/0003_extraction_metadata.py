"""add policy extraction metadata

Revision ID: 0003_extraction_metadata
Revises: 0002_plan_versions
Create Date: 2026-09-10

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_extraction_metadata"
down_revision: Union[str, Sequence[str], None] = "0002_plan_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plan_versions",
        sa.Column("extraction_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("plan_versions", "extraction_metadata", server_default=None)


def downgrade() -> None:
    op.drop_column("plan_versions", "extraction_metadata")
