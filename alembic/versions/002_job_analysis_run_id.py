"""add analysis_run_id to jobs

Revision ID: 002_job_analysis_run_id
Revises: 001_initial
Create Date: 2026-06-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "002_job_analysis_run_id"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("analysis_run_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_analysis_run_id",
        "jobs",
        "analysis_runs",
        ["analysis_run_id"],
        ["id"],
    )
    op.create_index("ix_jobs_analysis_run_id", "jobs", ["analysis_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_analysis_run_id", table_name="jobs")
    op.drop_constraint("fk_jobs_analysis_run_id", "jobs", type_="foreignkey")
    op.drop_column("jobs", "analysis_run_id")
