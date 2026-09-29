"""Registry schema (SQLAlchemy Core) -- design section 7, ADR-004.

The first Alembic migration (``alembic/versions/0001_initial.py``) creates exactly these
tables; a test compares the migrated database with this metadata so the two cannot drift.
Enumerations and the non-empty decision reason are enforced by ``CHECK`` constraints, the
one-shot holdout access by a ``UNIQUE`` constraint.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

RUN_STATUSES = ("running", "done", "failed", "aborted")
#: D-654, D-663: where a run's bars come from (the synthetic kinds are never mixed with real)
SOURCES = ("real", "null", "planted")
#: D-663: a funnel stage run can also be `empty` -- no input from upstream, nothing run
FUNNEL_STAGE_STATUSES = ("running", "done", "failed", "empty")
ARMS = ("real", "control")
CANDIDATE_STATUSES = ("active", "rejected", "approved", "retired")
DIRECTIONS = ("long", "short")
GATE_OPS = (">=", "<=", ">", "<", "==")
DECISIONS = ("approve", "reject", "return")

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join("'" + v + "'" for v in values)
    return f"{column} IN ({quoted})"


def _created() -> Column[Any]:
    return Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now())


pipeline_runs = Table(
    "pipeline_runs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("config", JSONB, nullable=False),
    Column("config_hash", Text, nullable=False),
    Column("code_version", Text, nullable=False),
    Column("seed", BigInteger, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("finished_at", DateTime(timezone=True)),
    Column("status", Text, nullable=False, server_default="running"),
    Column("notes", Text, nullable=False, server_default=""),
    # D-654, D-663 (migration 0002): real, or the synthetic kind the run's bars came from
    Column("source", Text, nullable=False, server_default="real"),
    CheckConstraint(_in("status", RUN_STATUSES), name="status"),
    CheckConstraint(_in("source", SOURCES), name="source"),
)

# Same key as the T02 catalog: one row per (content hash, source, symbol, timeframe).
SNAPSHOT_KEY = ("snapshot_hash", "source", "symbol", "timeframe")

data_snapshots = Table(
    "data_snapshots",
    metadata,
    Column("snapshot_hash", Text, primary_key=True),
    Column("source", Text, primary_key=True),
    Column("symbol", Text, primary_key=True),
    Column("timeframe", Text, primary_key=True),
    Column("is_reference", Boolean, nullable=False, server_default="false"),
    Column("meta", JSONB, nullable=False),
    Column("registered_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

splits = Table(
    "splits",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("snapshot_hash", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("symbol", Text, nullable=False),
    Column("timeframe", Text, nullable=False),
    Column("dev_start", DateTime(timezone=True), nullable=False),
    Column("dev_end", DateTime(timezone=True), nullable=False),
    Column("embargo_bars", Integer, nullable=False),
    Column("holdout_start", DateTime(timezone=True), nullable=False),
    Column("holdout_end", DateTime(timezone=True), nullable=False),
    Column("expected_holdout_trades", Float),
    _created(),
    ForeignKeyConstraint(list(SNAPSHOT_KEY), [f"data_snapshots.{c}" for c in SNAPSHOT_KEY]),
    UniqueConstraint(*SNAPSHOT_KEY),
    CheckConstraint("embargo_bars >= 0", name="embargo_nonnegative"),
)

candidates = Table(
    "candidates",
    metadata,
    Column("id", Text, primary_key=True),
    Column("parent_id", Text, ForeignKey("candidates.id")),
    Column("run_id", UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False),
    Column("symbol", Text, nullable=False),
    Column("timeframe", Text, nullable=False),
    Column("direction", Text, nullable=False),
    Column("edge_type", Text, nullable=False),
    Column("spec", JSONB, nullable=False),
    Column("spec_hash", Text, nullable=False),
    Column("current_stage", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="active"),
    _created(),
    CheckConstraint(_in("direction", DIRECTIONS), name="direction"),
    CheckConstraint(_in("status", CANDIDATE_STATUSES), name="status"),
    CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
)

trials = Table(
    "trials",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("run_id", UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False),
    Column("stage", Text, nullable=False),
    Column("candidate_id", Text, ForeignKey("candidates.id")),
    Column("family_id", Text, nullable=False),
    Column("spec_hash", Text, nullable=False),
    Column("params", JSONB, nullable=False),
    Column("n_trades", Integer),
    Column("net_profit", Float),
    Column("avg_annual_profit", Float),
    Column("avg_annual_dd_ystart", Float),
    Column("avg_annual_dd_peak", Float),
    Column("profit_dd_ratio", Float),
    Column("exposure", Float),
    Column("return_per_exposure", Float),
    Column("profit_factor", Float),
    Column("win_rate", Float),
    Column("expectancy_atr", Float),
    Column("extra", JSONB),
    _created(),
    Index(None, "run_id", "stage"),
    Index(None, "candidate_id"),
    Index(None, "family_id"),
)

gate_results = Table(
    "gate_results",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("run_id", UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False),
    Column("candidate_id", Text, ForeignKey("candidates.id"), nullable=False),
    Column("stage", Text, nullable=False),
    Column("criterion", Text, nullable=False),
    Column("metric_value", Float),
    Column("op", Text, nullable=False),
    Column("threshold", Float, nullable=False),
    Column("passed", Boolean, nullable=False),
    Column("critical", Boolean, nullable=False, server_default="false"),
    Column("reason", Text, nullable=False, server_default=""),
    _created(),
    CheckConstraint(_in("op", GATE_OPS), name="op"),
    Index(None, "candidate_id"),
)

artifacts = Table(
    "artifacts",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("run_id", UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False),
    Column("candidate_id", Text, ForeignKey("candidates.id")),
    Column("stage", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("path", Text, nullable=False),
    Column("schema_version", Text, nullable=False),
    Column("sha256", Text, nullable=False),
    _created(),
    Index(None, "candidate_id"),
)

holdout_access = Table(
    "holdout_access",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("candidate_id", Text, ForeignKey("candidates.id"), nullable=False, unique=True),
    Column("accessed_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("result", JSONB, nullable=False),
    Column("consumed", Boolean, nullable=False, server_default="true"),
)

reports = Table(
    "reports",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("candidate_id", Text, ForeignKey("candidates.id"), nullable=False),
    Column("docx_path", Text, nullable=False),
    Column("prompt_version", Text, nullable=False),
    Column("spec_version", Text, nullable=False),
    Column("verify_passed", Boolean, nullable=False),
    Column("verify_result", JSONB, nullable=False),
    _created(),
)

decisions = Table(
    "decisions",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("candidate_id", Text, ForeignKey("candidates.id"), nullable=False),
    Column("analyst", Text, nullable=False),
    Column("decision", Text, nullable=False),
    Column("return_to_stage", Text),
    Column("reason", Text, nullable=False),
    _created(),
    CheckConstraint(_in("decision", DECISIONS), name="decision"),
    CheckConstraint("length(btrim(reason)) > 0", name="reason_not_empty"),
    CheckConstraint("analyst <> ''", name="analyst_not_empty"),
    CheckConstraint(
        "decision <> 'return' OR return_to_stage IS NOT NULL", name="return_needs_stage"
    ),
)

# D-663 (T15a, migration 0002): one funnel run links its stage runs -- per timeframe, stage and
# arm (the real series and its reshuffled control, D-662) -- and resumes by `stage_key`.
funnel_runs = Table(
    "funnel_runs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("config", JSONB, nullable=False),
    Column("config_hash", Text, nullable=False),
    Column("funnel_key", Text, nullable=False),
    Column("code_version", Text, nullable=False),
    Column("seed", BigInteger, nullable=False),
    Column("source", Text, nullable=False, server_default="real"),
    Column("control", Boolean, nullable=False),  # false only with --no-control (D-653)
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("finished_at", DateTime(timezone=True)),
    Column("status", Text, nullable=False, server_default="running"),
    Column("notes", Text, nullable=False, server_default=""),
    CheckConstraint(_in("status", RUN_STATUSES), name="status"),
    CheckConstraint(_in("source", SOURCES), name="source"),
    Index(None, "funnel_key"),
)

funnel_stage_runs = Table(
    "funnel_stage_runs",
    metadata,
    Column("funnel_run_id", UUID(as_uuid=True), ForeignKey("funnel_runs.id"), primary_key=True),
    Column("timeframe", Text, primary_key=True),
    Column("stage", Text, primary_key=True),
    Column("arm", Text, primary_key=True),
    Column("stage_key", Text, nullable=False),
    Column("run_id", UUID(as_uuid=True), ForeignKey("pipeline_runs.id")),
    Column("status", Text, nullable=False, server_default="running"),
    Column("inputs", Integer),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("finished_at", DateTime(timezone=True)),
    CheckConstraint(_in("status", FUNNEL_STAGE_STATUSES), name="status"),
    CheckConstraint(_in("arm", ARMS), name="arm"),
)


ALL_TABLES = (
    pipeline_runs,
    data_snapshots,
    splits,
    candidates,
    trials,
    gate_results,
    artifacts,
    holdout_access,
    reports,
    decisions,
    funnel_runs,
    funnel_stage_runs,
)
