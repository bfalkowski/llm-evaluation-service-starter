"""add job attempt metadata

Revision ID: 20260526_0002
Revises: 20260524_0001
Create Date: 2026-05-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260526_0002"
down_revision: str | None = "20260524_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_jobs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_jobs",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "evaluation_jobs",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("evaluation_jobs", "attempt_count", server_default=None)
    op.alter_column("evaluation_jobs", "max_attempts", server_default=None)
    op.create_index("ix_evaluation_jobs_claimed_at", "evaluation_jobs", ["claimed_at"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_jobs_claimed_at", table_name="evaluation_jobs")
    op.drop_column("evaluation_jobs", "claimed_at")
    op.drop_column("evaluation_jobs", "max_attempts")
    op.drop_column("evaluation_jobs", "attempt_count")
