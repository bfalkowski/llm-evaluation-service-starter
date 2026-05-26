"""create evaluation jobs

Revision ID: 20260524_0001
Revises: 
Create Date: 2026-05-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260524_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("evaluation_jobs"):
        op.create_table(
            "evaluation_jobs",
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", sa.String(length=128), nullable=False),
            sa.Column("project_id", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("job_id"),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("evaluation_jobs")}
    if "ix_evaluation_jobs_project_id" not in existing_indexes:
        op.create_index("ix_evaluation_jobs_project_id", "evaluation_jobs", ["project_id"])
    if "ix_evaluation_jobs_status" not in existing_indexes:
        op.create_index("ix_evaluation_jobs_status", "evaluation_jobs", ["status"])
    if "ix_evaluation_jobs_tenant_id" not in existing_indexes:
        op.create_index("ix_evaluation_jobs_tenant_id", "evaluation_jobs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_jobs_tenant_id", table_name="evaluation_jobs")
    op.drop_index("ix_evaluation_jobs_status", table_name="evaluation_jobs")
    op.drop_index("ix_evaluation_jobs_project_id", table_name="evaluation_jobs")
    op.drop_table("evaluation_jobs")
