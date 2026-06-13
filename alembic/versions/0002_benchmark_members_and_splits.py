"""benchmark members + splits

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-13

Feature 004 (benchmark harness): the versioned, materialized benchmark. Adds
``benchmark_members`` (one row per (dataset_id, benchmark_version) fixed-factor descriptor) and
``benchmark_splits`` (the frozen, content-hashed train/val/test assignment). Both are keyed by
``(dataset_id, benchmark_version)`` so a new version coexists with the old and prior results stay
attributable (contracts/db-schema.md; mirrors src/ds_agent_loop/store.py).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmark_members",
        sa.Column("dataset_id", sa.String(), primary_key=True),
        sa.Column("benchmark_version", sa.String(), primary_key=True),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("provenance", sa.String(), nullable=False),
        sa.Column("target", sa.String(), nullable=False),
        sa.Column("primary_metric", sa.String(), nullable=False),
        sa.Column("metric_direction", sa.Integer(), nullable=False),
        sa.Column("budget", sa.Integer(), nullable=False),
        sa.Column("patience", sa.Integer()),
        sa.Column("feature_schema", JSONB()),
        sa.Column("feature_names", JSONB()),
        sa.Column("action_space", JSONB()),
        sa.Column("model_allowlist", JSONB()),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("created_ts", sa.String()),
    )
    op.create_table(
        "benchmark_splits",
        sa.Column("dataset_id", sa.String(), primary_key=True),
        sa.Column("benchmark_version", sa.String(), primary_key=True),
        sa.Column("train_idx", JSONB(), nullable=False),
        sa.Column("val_idx", JSONB(), nullable=False),
        sa.Column("test_idx", JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("stratified", sa.Boolean(), nullable=False),
        sa.Column("n_rows", sa.Integer(), nullable=False),
        sa.Column("created_ts", sa.String()),
    )


def downgrade() -> None:
    op.drop_table("benchmark_splits")
    op.drop_table("benchmark_members")
