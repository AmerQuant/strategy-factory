"""Registry writes (F-0.7.1, F-0.7.3, F-0.7.4).

* Trials are buffered and written with **psycopg COPY** in batches (default 5000 rows,
  configurable); the buffer is flushed on ``flush()``, ``close()`` and context exit.
* The second holdout access for a candidate raises :class:`HoldoutAccessError`; the rule is
  enforced by the ``UNIQUE(candidate_id)`` constraint of ``holdout_access`` in the database,
  so it holds across processes and connections.
* An empty decision reason is rejected (Python check + ``CHECK`` constraint).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import uuid
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Literal

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, insert, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from strategy_factory.core.errors import HoldoutAccessError, RegistryError
from strategy_factory.core.logging import get_logger
from strategy_factory.registry.tables import (
    SNAPSHOT_KEY,
    artifacts,
    candidates,
    data_snapshots,
    decisions,
    gate_results,
    holdout_access,
    pipeline_runs,
    reports,
    splits,
)

log = get_logger(__name__)

DEFAULT_BATCH_SIZE = 5000
TRIAL_COLUMNS: tuple[str, ...] = (
    "run_id",
    "stage",
    "candidate_id",
    "family_id",
    "spec_hash",
    "params",
    "n_trades",
    "net_profit",
    "avg_annual_profit",
    "avg_annual_dd_ystart",
    "avg_annual_dd_peak",
    "profit_dd_ratio",
    "exposure",
    "return_per_exposure",
    "profit_factor",
    "win_rate",
    "expectancy_atr",
    "extra",
)
_JSON_COLUMNS = {"params", "extra"}
_REQUIRED_TRIAL = ("run_id", "stage", "family_id", "spec_hash", "params")


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def config_hash(config: Mapping[str, Any]) -> str:
    """sha256 of the canonical JSON of ``config``."""
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()


def git_sha(cwd: Path | None = None) -> str:
    """HEAD commit of the checkout at ``cwd`` (default: this package's folder), else "unknown"."""
    where = cwd or Path(__file__).resolve().parent
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=where, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and len(sha) == 40 else "unknown"


# --------------------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------------------
class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CandidateRecord(_Record):
    id: str = Field(min_length=1)
    parent_id: str | None = None
    run_id: uuid.UUID
    symbol: str
    timeframe: str
    direction: Literal["long", "short"]
    edge_type: str
    spec: dict[str, Any]
    spec_hash: str
    current_stage: str
    status: Literal["active", "rejected", "approved", "retired"] = "active"


class TrialRecord(_Record):
    run_id: uuid.UUID
    stage: str
    candidate_id: str | None = None
    family_id: str
    spec_hash: str
    params: dict[str, Any]
    n_trades: int | None = None
    net_profit: float | None = None
    avg_annual_profit: float | None = None
    avg_annual_dd_ystart: float | None = None
    avg_annual_dd_peak: float | None = None
    profit_dd_ratio: float | None = None
    exposure: float | None = None
    return_per_exposure: float | None = None
    profit_factor: float | None = None
    win_rate: float | None = None
    expectancy_atr: float | None = None
    extra: dict[str, Any] | None = None


class GateResultRecord(_Record):
    run_id: uuid.UUID
    candidate_id: str
    stage: str
    criterion: str
    metric_value: float | None
    op: Literal[">=", "<=", ">", "<", "=="]
    threshold: float
    passed: bool
    critical: bool = False
    reason: str = ""


class SplitRecord(_Record):
    """A dev/embargo/holdout split of one catalog snapshot (key = T02 catalog key)."""

    snapshot_hash: str
    source: str
    symbol: str
    timeframe: str
    dev_start: dt.datetime
    dev_end: dt.datetime
    embargo_bars: int = Field(ge=0)
    holdout_start: dt.datetime
    holdout_end: dt.datetime
    expected_holdout_trades: float | None = None


# --------------------------------------------------------------------------------------
# Writer
# --------------------------------------------------------------------------------------
class RegistryWriter:
    """Batched registry writer; use as a context manager so the trial buffer is flushed."""

    def __init__(self, engine: Engine, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        if batch_size <= 0:
            raise RegistryError("batch_size must be positive", stage="registry")
        self.engine = engine
        self.batch_size = batch_size
        self._buffer: list[tuple[Any, ...]] = []
        self.trials_written = 0

    # -- context -------------------------------------------------------------------------
    def __enter__(self) -> RegistryWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self.flush()

    # -- runs ----------------------------------------------------------------------------
    def start_run(
        self, config: Mapping[str, Any], seed: int, notes: str = "", code_version: str | None = None
    ) -> uuid.UUID:
        run_id = uuid.uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                insert(pipeline_runs).values(
                    id=run_id,
                    config=dict(config),
                    config_hash=config_hash(config),
                    code_version=code_version or git_sha(),
                    seed=seed,
                    status="running",
                    notes=notes,
                )
            )
        log.info("registry: run %s started (seed %d)", run_id, seed)
        return run_id

    def finish_run(self, run_id: uuid.UUID, status: str) -> None:
        if status not in ("done", "failed", "aborted"):
            raise RegistryError(f"invalid final run status {status!r}", stage="registry")
        self.flush()
        with self.engine.begin() as conn:
            res = conn.execute(
                update(pipeline_runs)
                .where(pipeline_runs.c.id == run_id)
                .values(status=status, finished_at=dt.datetime.now(dt.UTC))
            )
        if res.rowcount != 1:
            raise RegistryError(f"unknown run {run_id}", stage="registry")

    # -- reference data ------------------------------------------------------------------
    def register_snapshot(self, meta: Mapping[str, Any], is_reference: bool = False) -> None:
        """Mirror a catalog snapshot (metadata as JSON).

        Upsert on the catalog key ``(snapshot_hash, source, symbol, timeframe)``: identical
        content under another source/symbol/timeframe is a separate row, as in the T02 catalog.
        """
        stmt = pg_insert(data_snapshots).values(
            snapshot_hash=meta["snapshot_hash"],
            source=meta["source"],
            symbol=meta["symbol"],
            timeframe=meta["timeframe"],
            is_reference=is_reference,
            meta=json.loads(canonical_json(meta)),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[data_snapshots.c[c] for c in SNAPSHOT_KEY],
            set_={"is_reference": stmt.excluded.is_reference, "meta": stmt.excluded.meta},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def add_split(self, split: SplitRecord) -> int:
        with self.engine.begin() as conn:
            res = conn.execute(insert(splits).values(**split.model_dump()).returning(splits.c.id))
            return int(res.scalar_one())

    # -- candidates ----------------------------------------------------------------------
    def upsert_candidate(self, candidate: CandidateRecord) -> None:
        values = candidate.model_dump()
        stmt = pg_insert(candidates).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[candidates.c.id],
            set_={"current_stage": stmt.excluded.current_stage, "status": stmt.excluded.status},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    # -- trials (COPY) -------------------------------------------------------------------
    def add_trials(self, rows: Iterable[TrialRecord | Mapping[str, Any]]) -> None:
        """Buffer trial rows; COPY them in batches of ``batch_size``."""
        for row in rows:
            data = row.model_dump() if isinstance(row, TrialRecord) else row
            missing = [k for k in _REQUIRED_TRIAL if data.get(k) is None]
            if missing:
                raise RegistryError(f"trial row misses {missing}", stage="registry")
            unknown = set(data) - set(TRIAL_COLUMNS)
            if unknown:
                raise RegistryError(f"unknown trial fields {sorted(unknown)}", stage="registry")
            self._buffer.append(
                tuple(
                    Jsonb(data[c])
                    if c in _JSON_COLUMNS and data.get(c) is not None
                    else data.get(c)
                    for c in TRIAL_COLUMNS
                )
            )
            if len(self._buffer) >= self.batch_size:
                self.flush()

    def flush(self) -> int:
        """Write the buffered trials with one COPY; returns the number of rows written."""
        if not self._buffer:
            return 0
        rows, self._buffer = self._buffer, []
        cols = ", ".join(TRIAL_COLUMNS)
        raw = self.engine.raw_connection()
        try:
            pg = raw.driver_connection
            assert pg is not None
            with pg.cursor() as cur, cur.copy(f"COPY trials ({cols}) FROM STDIN") as copy:
                for r in rows:
                    copy.write_row(r)
            pg.commit()
        except Exception as exc:
            raw.rollback()
            self._buffer = rows + self._buffer  # keep them; the caller decides
            raise RegistryError(
                f"COPY of {len(rows)} trials failed ({type(exc).__name__}: {exc})", stage="registry"
            ) from exc
        finally:
            raw.close()
        self.trials_written += len(rows)
        return len(rows)

    @property
    def buffered(self) -> int:
        return len(self._buffer)

    # -- gates, artifacts, reports, decisions ----------------------------------------------
    def add_gate_results(self, rows: Sequence[GateResultRecord]) -> None:
        if not rows:
            return
        with self.engine.begin() as conn:
            conn.execute(insert(gate_results), [r.model_dump() for r in rows])

    def add_artifact(
        self,
        run_id: uuid.UUID,
        stage: str,
        kind: str,
        path: str,
        schema_version: str,
        sha256: str,
        candidate_id: str | None = None,
    ) -> int:
        with self.engine.begin() as conn:
            res = conn.execute(
                insert(artifacts)
                .values(
                    run_id=run_id,
                    candidate_id=candidate_id,
                    stage=stage,
                    kind=kind,
                    path=path,
                    schema_version=schema_version,
                    sha256=sha256,
                )
                .returning(artifacts.c.id)
            )
            return int(res.scalar_one())

    def add_report(
        self,
        candidate_id: str,
        docx_path: str,
        prompt_version: str,
        spec_version: str,
        verify_passed: bool,
        verify_result: Mapping[str, Any],
    ) -> int:
        with self.engine.begin() as conn:
            res = conn.execute(
                insert(reports)
                .values(
                    candidate_id=candidate_id,
                    docx_path=docx_path,
                    prompt_version=prompt_version,
                    spec_version=spec_version,
                    verify_passed=verify_passed,
                    verify_result=dict(verify_result),
                )
                .returning(reports.c.id)
            )
            return int(res.scalar_one())

    def add_decision(
        self,
        candidate_id: str,
        analyst: str,
        decision: Literal["approve", "reject", "return"],
        reason: str,
        return_to_stage: str | None = None,
    ) -> int:
        if not reason or not reason.strip():
            raise RegistryError(
                "a decision needs a non-empty reason", stage="decision", config_path=None
            )
        if decision == "return" and not return_to_stage:
            raise RegistryError("decision 'return' needs return_to_stage", stage="decision")
        with self.engine.begin() as conn:
            res = conn.execute(
                insert(decisions)
                .values(
                    candidate_id=candidate_id,
                    analyst=analyst,
                    decision=decision,
                    return_to_stage=return_to_stage,
                    reason=reason,
                )
                .returning(decisions.c.id)
            )
            return int(res.scalar_one())

    # -- holdout ---------------------------------------------------------------------------
    def record_holdout_access(self, candidate_id: str, result: Mapping[str, Any]) -> int:
        """One-shot holdout access; a second call for the candidate raises HoldoutAccessError."""
        try:
            with self.engine.begin() as conn:
                res = conn.execute(
                    insert(holdout_access)
                    .values(candidate_id=candidate_id, result=dict(result), consumed=True)
                    .returning(holdout_access.c.id)
                )
                return int(res.scalar_one())
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":  # unique_violation
                raise HoldoutAccessError(
                    f"holdout already accessed for candidate {candidate_id!r} (one-shot rule)",
                    stage="holdout",
                    symbol=None,
                ) from None
            raise RegistryError(
                f"holdout access could not be recorded ({type(exc.orig).__name__})",
                stage="holdout",
            ) from exc
