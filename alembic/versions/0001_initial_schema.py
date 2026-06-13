"""initial ablation schema

Revision ID: 0001
Revises:
Create Date: 2026-06-13

Baseline schema for the memory-compaction ablation: cells, experiment_records,
memory_views, compaction_artifacts, run_logs (mirrors src/ds_agent_loop/store.py;
contracts/db-schema.md). Future schema changes ship as new revisions on top of this one.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cells",
        sa.Column("cell_id", sa.String(), primary_key=True),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("regime", sa.String(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("k", sa.Integer(), nullable=False),
        sa.Column("m", sa.Integer(), nullable=False),
        sa.Column("budget", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.String()),
        sa.Column("last_iteration", sa.Integer()),
        sa.Column("repro", JSONB()),
        sa.Column("created_ts", sa.String()),
        sa.Column("updated_ts", sa.String()),
    )
    op.create_table(
        "experiment_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cell_id", sa.String(), nullable=False),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.String()),
        sa.Column("regime", sa.String()),
        sa.Column("seed", sa.Integer()),
        sa.Column("k", sa.Integer()),
        sa.Column("m", sa.Integer()),
        sa.Column("dataset_size", sa.Integer()),
        sa.Column("model_name", sa.String()),
        sa.Column("hyperparameters", JSONB()),
        sa.Column("proposal", JSONB()),
        sa.Column("executed_config", JSONB()),
        sa.Column("metrics", JSONB()),
        sa.Column("val_metrics", JSONB()),
        sa.Column("test_metrics", JSONB()),
        sa.Column("improved", sa.Boolean()),
        sa.Column("rejected", sa.Boolean()),
        sa.Column("memory_view_ref", sa.String()),
        sa.Column("runtime_s", sa.Float()),
        sa.Column("rationale", sa.String()),
        sa.Column("timestamp", sa.String()),
        sa.UniqueConstraint("cell_id", "iteration", name="uq_record_cell_iter"),
    )
    op.create_table(
        "memory_views",
        sa.Column("cell_id", sa.String(), nullable=False),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("regime", sa.String(), nullable=False),
        sa.Column("included_record_ids", JSONB()),
        sa.Column("included_artifact_id", sa.String()),
        sa.Column("rendered_text", sa.String()),
        sa.Column("content_hash", sa.String()),
        sa.Column("prompt_token_count", sa.Integer()),
        sa.UniqueConstraint("cell_id", "iteration", name="uq_view_cell_iter"),
    )
    op.create_table(
        "compaction_artifacts",
        sa.Column("artifact_id", sa.String(), primary_key=True),
        sa.Column("cell_id", sa.String(), nullable=False),
        sa.Column("trigger_iteration", sa.Integer(), nullable=False),
        sa.Column("artifact", JSONB()),
        sa.Column("source_record_ids", JSONB()),
        sa.Column("created_ts", sa.String()),
        sa.UniqueConstraint("cell_id", "trigger_iteration", name="uq_artifact_cell_trigger"),
    )
    op.create_table(
        "run_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cell_id", sa.String()),
        sa.Column("iteration", sa.Integer()),
        sa.Column("level", sa.String()),
        sa.Column("event", sa.String()),
        sa.Column("payload", JSONB()),
        sa.Column("ts", sa.String()),
    )


def downgrade() -> None:
    op.drop_table("run_logs")
    op.drop_table("compaction_artifacts")
    op.drop_table("memory_views")
    op.drop_table("experiment_records")
    op.drop_table("cells")
