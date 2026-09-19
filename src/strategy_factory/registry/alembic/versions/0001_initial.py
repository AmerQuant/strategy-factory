"""Initial registry schema (T03, design section 7).

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def _created() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column("created_at", TZ, nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("config", pg.JSONB(), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("code_version", sa.Text(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("started_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", TZ),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_runs"),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed', 'aborted')", name="ck_pipeline_runs_status"
        ),
    )
    op.create_table(
        "data_snapshots",
        sa.Column("snapshot_hash", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column("is_reference", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("meta", pg.JSONB(), nullable=False),
        sa.Column("registered_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint(
            "snapshot_hash", "source", "symbol", "timeframe", name="pk_data_snapshots"
        ),
    )
    op.create_table(
        "splits",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("snapshot_hash", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column("dev_start", TZ, nullable=False),
        sa.Column("dev_end", TZ, nullable=False),
        sa.Column("embargo_bars", sa.Integer(), nullable=False),
        sa.Column("holdout_start", TZ, nullable=False),
        sa.Column("holdout_end", TZ, nullable=False),
        sa.Column("expected_holdout_trades", sa.Float()),
        _created(),
        sa.PrimaryKeyConstraint("id", name="pk_splits"),
        sa.ForeignKeyConstraint(
            ["snapshot_hash", "source", "symbol", "timeframe"],
            [
                "data_snapshots.snapshot_hash",
                "data_snapshots.source",
                "data_snapshots.symbol",
                "data_snapshots.timeframe",
            ],
            name="fk_splits_snapshot_hash_data_snapshots",
        ),
        sa.UniqueConstraint(
            "snapshot_hash",
            "source",
            "symbol",
            "timeframe",
            name="uq_splits_snapshot_hash_source_symbol_timeframe",
        ),
        sa.CheckConstraint("embargo_bars >= 0", name="ck_splits_embargo_nonnegative"),
    )
    op.create_table(
        "candidates",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.Text()),
        sa.Column("run_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("edge_type", sa.Text(), nullable=False),
        sa.Column("spec", pg.JSONB(), nullable=False),
        sa.Column("spec_hash", sa.Text(), nullable=False),
        sa.Column("current_stage", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        _created(),
        sa.PrimaryKeyConstraint("id", name="pk_candidates"),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["candidates.id"], name="fk_candidates_parent_id_candidates"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_candidates_run_id_pipeline_runs"
        ),
        sa.CheckConstraint("direction IN ('long', 'short')", name="ck_candidates_direction"),
        sa.CheckConstraint(
            "status IN ('active', 'rejected', 'approved', 'retired')", name="ck_candidates_status"
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="ck_candidates_not_own_parent"
        ),
    )
    op.create_table(
        "trials",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("run_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("candidate_id", sa.Text()),
        sa.Column("family_id", sa.Text(), nullable=False),
        sa.Column("spec_hash", sa.Text(), nullable=False),
        sa.Column("params", pg.JSONB(), nullable=False),
        sa.Column("n_trades", sa.Integer()),
        sa.Column("net_profit", sa.Float()),
        sa.Column("avg_annual_profit", sa.Float()),
        sa.Column("avg_annual_dd_ystart", sa.Float()),
        sa.Column("avg_annual_dd_peak", sa.Float()),
        sa.Column("profit_dd_ratio", sa.Float()),
        sa.Column("exposure", sa.Float()),
        sa.Column("return_per_exposure", sa.Float()),
        sa.Column("profit_factor", sa.Float()),
        sa.Column("win_rate", sa.Float()),
        sa.Column("expectancy_atr", sa.Float()),
        sa.Column("extra", pg.JSONB()),
        _created(),
        sa.PrimaryKeyConstraint("id", name="pk_trials"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_trials_run_id_pipeline_runs"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="fk_trials_candidate_id_candidates"
        ),
    )
    op.create_index("ix_trials_run_id_stage", "trials", ["run_id", "stage"])
    op.create_index("ix_trials_candidate_id", "trials", ["candidate_id"])
    op.create_index("ix_trials_family_id", "trials", ["family_id"])
    op.create_table(
        "gate_results",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("run_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("criterion", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Float()),
        sa.Column("op", sa.Text(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("critical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        _created(),
        sa.PrimaryKeyConstraint("id", name="pk_gate_results"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_gate_results_run_id_pipeline_runs"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="fk_gate_results_candidate_id_candidates"
        ),
        sa.CheckConstraint("op IN ('>=', '<=', '>', '<', '==')", name="ck_gate_results_op"),
    )
    op.create_index("ix_gate_results_candidate_id", "gate_results", ["candidate_id"])
    op.create_table(
        "artifacts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("run_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", sa.Text()),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        _created(),
        sa.PrimaryKeyConstraint("id", name="pk_artifacts"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_artifacts_run_id_pipeline_runs"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="fk_artifacts_candidate_id_candidates"
        ),
    )
    op.create_index("ix_artifacts_candidate_id", "artifacts", ["candidate_id"])
    op.create_table(
        "holdout_access",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("candidate_id", sa.Text(), nullable=False),
        sa.Column("accessed_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("result", pg.JSONB(), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id", name="pk_holdout_access"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="fk_holdout_access_candidate_id_candidates"
        ),
        sa.UniqueConstraint("candidate_id", name="uq_holdout_access_candidate_id"),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("candidate_id", sa.Text(), nullable=False),
        sa.Column("docx_path", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("spec_version", sa.Text(), nullable=False),
        sa.Column("verify_passed", sa.Boolean(), nullable=False),
        sa.Column("verify_result", pg.JSONB(), nullable=False),
        _created(),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="fk_reports_candidate_id_candidates"
        ),
    )
    op.create_table(
        "decisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("candidate_id", sa.Text(), nullable=False),
        sa.Column("analyst", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("return_to_stage", sa.Text()),
        sa.Column("reason", sa.Text(), nullable=False),
        _created(),
        sa.PrimaryKeyConstraint("id", name="pk_decisions"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="fk_decisions_candidate_id_candidates"
        ),
        sa.CheckConstraint(
            "decision IN ('approve', 'reject', 'return')", name="ck_decisions_decision"
        ),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_decisions_reason_not_empty"),
        sa.CheckConstraint("analyst <> ''", name="ck_decisions_analyst_not_empty"),
        sa.CheckConstraint(
            "decision <> 'return' OR return_to_stage IS NOT NULL",
            name="ck_decisions_return_needs_stage",
        ),
    )


def downgrade() -> None:
    for table in (
        "decisions",
        "reports",
        "holdout_access",
        "artifacts",
        "gate_results",
        "trials",
        "candidates",
        "splits",
        "data_snapshots",
        "pipeline_runs",
    ):
        op.drop_table(table)
