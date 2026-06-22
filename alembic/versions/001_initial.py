"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-06-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_id", "users", ["id"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("stored_pdf_path", sa.String(length=1024), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "file_sha256", name="uq_user_file_sha256"),
    )
    op.create_index("ix_documents_file_sha256", "documents", ["file_sha256"], unique=False)
    op.create_index("ix_documents_id", "documents", ["id"], unique=False)
    op.create_index("ix_documents_user_id", "documents", ["user_id"], unique=False)

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("global_is_compliant", sa.Boolean(), nullable=True),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        sa.Column("document_type", sa.String(length=255), nullable=True),
        sa.Column("certificate_date", sa.String(length=128), nullable=True),
        sa.Column("total_items_detected", sa.Integer(), nullable=True),
        sa.Column("ai_analysis_remarks", sa.Text(), nullable=True),
        sa.Column("raw_response_json", sa.Text(), nullable=True),
        sa.Column("preprocessing_meta_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analysis_runs_document_id", "analysis_runs", ["document_id"], unique=False)
    op.create_index("ix_analysis_runs_id", "analysis_runs", ["id"], unique=False)
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"], unique=False)
    op.create_index("ix_analysis_runs_user_id", "analysis_runs", ["user_id"], unique=False)

    op.create_table(
        "analysis_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=255), nullable=True),
        sa.Column("heat_number", sa.String(length=255), nullable=True),
        sa.Column("grade", sa.String(length=255), nullable=True),
        sa.Column("weight_or_length", sa.String(length=255), nullable=True),
        sa.Column("yield_strength_mpa", sa.Float(), nullable=True),
        sa.Column("tensile_strength_mpa", sa.Float(), nullable=True),
        sa.Column("elongation_percentage", sa.Float(), nullable=True),
        sa.Column("row_is_compliant", sa.Boolean(), nullable=True),
        sa.Column("deviations_json", sa.Text(), nullable=True),
        sa.Column("row_confidence", sa.Float(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_analysis_items_analysis_run_id", "analysis_items", ["analysis_run_id"], unique=False)
    op.create_index("ix_analysis_items_id", "analysis_items", ["id"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_object_key", sa.String(length=1024), nullable=False),
        sa.Column("result_object_key", sa.String(length=1024), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_id", "jobs", ["id"], unique=False)
    op.create_index("ix_jobs_status", "jobs", ["status"], unique=False)
    op.create_index("ix_jobs_trace_id", "jobs", ["trace_id"], unique=False)
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("analysis_items")
    op.drop_table("analysis_runs")
    op.drop_table("documents")
    op.drop_table("users")
