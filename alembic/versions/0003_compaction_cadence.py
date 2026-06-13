"""compaction cadence + trigger mode

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-13

Feature 006 (compaction operator): record the cadence with every artifact. Adds two additive,
nullable columns to ``compaction_artifacts`` — ``cadence`` (the explicit ``m`` in effect at the
trigger, FR-004) and ``trigger_mode`` (``fixed`` | ``compact_over_what_exists`` |
``token_threshold``, FR-006). Existing rows read back ``NULL`` (treated as "cadence unrecorded —
pre-006"); no data backfill (FR-006b). Reversible: ``downgrade`` drops both columns, matching the
0002 acceptance bar (upgrade → downgrade → upgrade verified, idempotent).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("compaction_artifacts", sa.Column("cadence", sa.Integer(), nullable=True))
    op.add_column("compaction_artifacts", sa.Column("trigger_mode", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("compaction_artifacts", "trigger_mode")
    op.drop_column("compaction_artifacts", "cadence")
