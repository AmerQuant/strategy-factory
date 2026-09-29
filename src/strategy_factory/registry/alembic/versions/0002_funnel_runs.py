"""The funnel-run link (T15a, D-663): funnel_runs, funnel_stage_runs, pipeline_runs.source.

Revision ID: 0002_funnel_runs
Revises: 0001_initial
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002_funnel_runs"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
SOURCES = "source IN ('real', 'null', 'planted')"


def upgrade() -> None:
    op.add_column(
        "pipeline_runs",
        sa.Column("source", sa.Text(), nullable=False, server_default="real"),
    )
    op.create_check_constraint("ck_pipeline_runs_source", "pipeline_runs", SOURCES)
    op.create_table(
        "funnel_runs",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("config", pg.JSONB(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("funnel_key", sa.Text(), nullable=False),
        sa.Column("code_version", sa.Text(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="real"),
        sa.Column("control", sa.Boolean(), nullable=False),
        sa.Column("started_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", TZ),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id", name="pk_funnel_runs"),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed', 'aborted')", name="ck_funnel_runs_status"
        ),
        sa.CheckConstraint(SOURCES, name="ck_funnel_runs_source"),
    )
    op.create_index("ix_funnel_runs_funnel_key", "funnel_runs", ["funnel_key"])
    op.create_table(
        "funnel_stage_runs",
        sa.Column("funnel_run_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("arm", sa.Text(), nullable=False),
        sa.Column("stage_key", sa.Text(), nullable=False),
        sa.Column("run_id", pg.UUID(as_uuid=True)),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("inputs", sa.Integer()),
        sa.Column("started_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", TZ),
        sa.PrimaryKeyConstraint(
            "funnel_run_id", "timeframe", "stage", "arm", name="pk_funnel_stage_runs"
        ),
        sa.ForeignKeyConstraint(
            ["funnel_run_id"],
            ["funnel_runs.id"],
            name="fk_funnel_stage_runs_funnel_run_id_funnel_runs",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_funnel_stage_runs_run_id_pipeline_runs"
        ),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed', 'empty')", name="ck_funnel_stage_runs_status"
        ),
        sa.CheckConstraint("arm IN ('real', 'control')", name="ck_funnel_stage_runs_arm"),
    )


def downgrade() -> None:
    op.drop_table("funnel_stage_runs")
    op.drop_index("ix_funnel_runs_funnel_key", table_name="funnel_runs")
    op.drop_table("funnel_runs")
    op.drop_constraint("ck_pipeline_runs_source", "pipeline_runs", type_="check")
    op.drop_column("pipeline_runs", "source")
