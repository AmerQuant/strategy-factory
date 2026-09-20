"""F-0.7.1: registry round trips, COPY batches, buffer flush; migrations; secrets."""

from __future__ import annotations

import datetime as dt
import logging
import time
import uuid

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, func, inspect, select

from strategy_factory.core.errors import RegistryError
from strategy_factory.registry import tables as T
from strategy_factory.registry.engine import make_engine
from strategy_factory.registry.migrations import (
    current_revision,
    downgrade,
    head_revision,
    row_counts,
    upgrade,
)
from strategy_factory.registry.writer import (
    CandidateRecord,
    GateResultRecord,
    RegistryWriter,
    SplitRecord,
    TrialRecord,
    config_hash,
)

T0 = dt.datetime(2024, 1, 2, tzinfo=dt.UTC)
CONFIG = {
    "pipeline": "mvp_daily",
    "data_snapshots": {"SPY": {"1D": {"source": "alpaca", "snapshot_hash": "a" * 64}}},
    "seed": 7,
}


def one(engine: Engine, table: object) -> dict[str, object]:
    with engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(select(table))]  # type: ignore[call-overload]
    assert len(rows) == 1
    return rows[0]


def candidate(run_id: uuid.UUID, cid: str = "cand-1", parent: str | None = None) -> CandidateRecord:
    return CandidateRecord(
        id=cid,
        parent_id=parent,
        run_id=run_id,
        symbol="SPY",
        timeframe="1D",
        direction="long",
        edge_type="MR",
        spec={"entry": {"name": "rsi_threshold", "params": {"n": 2}}},
        spec_hash="s" * 64,
        current_stage="s01_edge",
    )


def trial_row(run_id: uuid.UUID, i: int, cid: str | None = "cand-1") -> dict[str, object]:
    return {
        "run_id": run_id,
        "stage": "s03_entry",
        "candidate_id": cid,
        "family_id": "fam-rsi",
        "spec_hash": "s" * 64,
        "params": {"n": i % 10, "thr": 5 + i % 7},
        "n_trades": 100 + i % 50,
        "net_profit": 1000.0 + i,
        "avg_annual_profit": 10.5,
        "avg_annual_dd_ystart": -4.0,
        "avg_annual_dd_peak": -5.0,
        "profit_dd_ratio": 2.6,
        "exposure": 0.3,
        "return_per_exposure": 35.0,
        "profit_factor": 1.4,
        "win_rate": 0.55,
        "expectancy_atr": 0.12,
        "extra": {"i": i},
    }


# -- round trip of each table ------------------------------------------------------------
@pytest.mark.db
def test_F_0_7_1_round_trip_every_table(registry_engine: Engine) -> None:
    w = RegistryWriter(registry_engine)
    run_id = w.start_run(CONFIG, seed=7, code_version="c" * 40)
    run = one(registry_engine, T.pipeline_runs)
    assert run["config"] == CONFIG and run["config_hash"] == config_hash(CONFIG)
    assert (run["code_version"], run["seed"], run["status"]) == ("c" * 40, 7, "running")

    snapshot = {
        "snapshot_hash": "a" * 64,
        "source": "alpaca",
        "symbol": "SPY",
        "timeframe": "1D",
        "row_count": 10,
    }
    w.register_snapshot(snapshot, is_reference=True)
    snap = one(registry_engine, T.data_snapshots)
    assert snap["is_reference"] is True and snap["meta"]["row_count"] == 10

    split_id = w.add_split(
        SplitRecord(
            snapshot_hash="a" * 64,
            source="alpaca",
            symbol="SPY",
            timeframe="1D",
            dev_start=T0,
            dev_end=T0 + dt.timedelta(days=900),
            embargo_bars=60,
            holdout_start=T0 + dt.timedelta(days=960),
            holdout_end=T0 + dt.timedelta(days=1400),
            expected_holdout_trades=42.0,
        )
    )
    assert one(registry_engine, T.splits)["id"] == split_id

    w.upsert_candidate(candidate(run_id))
    w.upsert_candidate(candidate(run_id).model_copy(update={"current_stage": "s02_method"}))
    cand = one(registry_engine, T.candidates)
    assert cand["current_stage"] == "s02_method" and cand["spec"]["entry"]["params"] == {"n": 2}

    with w:
        w.add_trials([TrialRecord(**trial_row(run_id, 1))])  # type: ignore[arg-type]
    tr = one(registry_engine, T.trials)
    assert tr["params"] == {"n": 1, "thr": 6} and tr["extra"] == {"i": 1} and tr["n_trades"] == 101

    gate = GateResultRecord(
        run_id=run_id,
        candidate_id="cand-1",
        stage="s03_entry",
        criterion="profit_dd_ratio",
        metric_value=2.6,
        op=">=",
        threshold=2.0,
        passed=True,
        critical=False,
        reason="ok",
    )
    w.add_gate_results([gate])
    assert one(registry_engine, T.gate_results)["passed"] is True
    art = w.add_artifact(
        run_id, "s03_entry", "equity_curve", "artifacts/x.parquet", "1", "f" * 64, "cand-1"
    )
    assert one(registry_engine, T.artifacts)["id"] == art
    w.record_holdout_access("cand-1", {"net_profit": 5.0})
    assert one(registry_engine, T.holdout_access)["consumed"] is True
    w.add_report("cand-1", "r.docx", "p1", "s1", True, {"checked": 12})
    assert one(registry_engine, T.reports)["verify_result"] == {"checked": 12}
    w.add_decision("cand-1", "analyst-a", "return", "needs more OOS", return_to_stage="s06_robust")
    assert one(registry_engine, T.decisions)["return_to_stage"] == "s06_robust"

    w.finish_run(run_id, "done")
    run = one(registry_engine, T.pipeline_runs)
    assert run["status"] == "done" and run["finished_at"] is not None
    assert set(row_counts(registry_engine).values()) == {1}


@pytest.mark.db
def test_F_0_7_1_data_snapshots_key_matches_catalog(registry_engine: Engine) -> None:
    """Composite key (snapshot_hash, source, symbol, timeframe), as in the T02 catalog."""
    from sqlalchemy.exc import IntegrityError

    w = RegistryWriter(registry_engine)
    h = "b" * 64
    base = {"snapshot_hash": h, "source": "alpaca", "symbol": "SPY", "timeframe": "1D"}
    w.register_snapshot(base, is_reference=True)
    w.register_snapshot({**base, "source": "yahoo"})  # same content, other source
    w.register_snapshot({**base, "symbol": "IVV"})  # same content, other symbol
    w.register_snapshot({**base, "note": "updated"}, is_reference=False)  # upsert, same key
    with registry_engine.connect() as conn:
        rows = conn.execute(
            select(
                T.data_snapshots.c.source,
                T.data_snapshots.c.symbol,
                T.data_snapshots.c.is_reference,
            ).order_by(T.data_snapshots.c.source, T.data_snapshots.c.symbol)
        ).all()
    assert [tuple(r) for r in rows] == [
        ("alpaca", "IVV", False),
        ("alpaca", "SPY", False),
        ("yahoo", "SPY", False),
    ]
    pk = inspect(registry_engine).get_pk_constraint("data_snapshots")["constrained_columns"]
    assert pk == ["snapshot_hash", "source", "symbol", "timeframe"]

    split = SplitRecord(
        **base,
        dev_start=T0,
        dev_end=T0 + dt.timedelta(days=900),
        embargo_bars=5,
        holdout_start=T0 + dt.timedelta(days=910),
        holdout_end=T0 + dt.timedelta(days=1300),
    )
    w.add_split(split)
    w.add_split(split.model_copy(update={"source": "yahoo"}))  # other registered snapshot
    with pytest.raises(IntegrityError):  # the full key must exist in data_snapshots
        w.add_split(split.model_copy(update={"source": "dukascopy"}))
    with pytest.raises(IntegrityError):  # one split per snapshot key
        w.add_split(split)


# -- COPY ------------------------------------------------------------------------------------
@pytest.mark.db
def test_F_0_7_1_copy_100k_trials(
    registry_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    w = RegistryWriter(registry_engine)  # default batch 5000
    run_id = w.start_run(CONFIG, seed=1, code_version="c" * 40)
    w.upsert_candidate(candidate(run_id))
    n = 100_000
    t0 = time.perf_counter()
    with w:
        w.add_trials(trial_row(run_id, i) for i in range(n))
    elapsed = time.perf_counter() - t0
    with registry_engine.connect() as conn:
        count = conn.execute(select(func.count()).select_from(T.trials)).scalar_one()
    assert count == n == w.trials_written
    with capsys.disabled():
        print(f"\n[F-0.7.1] COPY of {n:,} trials: {elapsed:.2f} s ({n / elapsed:,.0f} rows/s)")


@pytest.mark.db
def test_F_0_7_1_buffer_flushes_at_batch_size_and_on_close(registry_engine: Engine) -> None:
    w = RegistryWriter(registry_engine, batch_size=10)
    run_id = w.start_run(CONFIG, seed=1, code_version="c" * 40)

    def count() -> int:
        with registry_engine.connect() as conn:
            return int(conn.execute(select(func.count()).select_from(T.trials)).scalar_one())

    w.add_trials(trial_row(run_id, i, None) for i in range(25))
    assert count() == 20 and w.buffered == 5  # two automatic flushes at 10 rows
    w.close()
    assert count() == 25 and w.buffered == 0


@pytest.mark.db
def test_F_0_7_1_trial_rows_are_validated(registry_engine: Engine) -> None:
    w = RegistryWriter(registry_engine)
    run_id = w.start_run(CONFIG, seed=1, code_version="c" * 40)
    with pytest.raises(RegistryError, match="misses"):
        w.add_trials([{"run_id": run_id, "stage": "s01"}])
    with pytest.raises(RegistryError, match="unknown trial fields"):
        w.add_trials([{**trial_row(run_id, 1, None), "sharpe": 1.0}])


@pytest.mark.db
def test_F_0_7_1_config_hash_and_git_sha(registry_engine: Engine) -> None:
    from strategy_factory.registry.writer import DIRTY_SUFFIX

    w = RegistryWriter(registry_engine)
    run_id = w.start_run(CONFIG, seed=3)
    run = one(registry_engine, T.pipeline_runs)
    assert run["id"] == run_id
    assert config_hash({"b": 1, "a": 2}) == config_hash({"a": 2, "b": 1})
    # T10b: <sha>, <sha>-dirty or unknown (the dirty flag is stored, never hashed)
    version = str(run["code_version"])
    assert version == "unknown" or len(version.removesuffix(DIRTY_SUFFIX)) == 40


# -- migrations ------------------------------------------------------------------------------
@pytest.mark.db
def test_F_0_7_1_migrations_up_down_up_and_match_tables(registry_engine: Engine) -> None:
    assert current_revision(registry_engine) == head_revision() == "0001_initial"
    downgrade(registry_engine, "base")
    assert current_revision(registry_engine) is None
    assert set(inspect(registry_engine).get_table_names()) <= {"alembic_version"}
    upgrade(registry_engine, "head")
    assert current_revision(registry_engine) == "0001_initial"
    with registry_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), T.metadata)
    assert diff == []  # migration and tables.py describe the same schema
    names = {t.name for t in T.ALL_TABLES}
    assert names <= set(inspect(registry_engine).get_table_names())


# -- secrets (no database needed) --------------------------------------------------------
FAKE_PASSWORD = "Sup3rS3cretPw!9"


def test_F_0_7_1_db_password_never_in_errors_or_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: object
) -> None:
    url = f"postgresql+psycopg://sfac:{FAKE_PASSWORD}@127.0.0.1:1/nodb"
    caplog.set_level(logging.DEBUG)
    logging.getLogger("strategy_factory").propagate = True
    try:
        with pytest.raises(RegistryError) as exc:
            make_engine(url, connect_timeout=2)
        monkeypatch.setenv("SFAC_DB_URL", url)
        with pytest.raises(RegistryError) as exc2:
            make_engine(connect_timeout=2)
        with pytest.raises(RegistryError) as exc3:
            make_engine("not a url " + FAKE_PASSWORD)
    finally:
        logging.getLogger("strategy_factory").propagate = False
    for e in (exc.value, exc2.value, exc3.value):
        text = f"{e} {e!r} {e.__cause__!r} {e.__context__!r}"
        assert FAKE_PASSWORD not in text and "127.0.0.1:1" not in text
    assert "cannot connect" in str(exc.value)
    for rec in caplog.records:
        assert FAKE_PASSWORD not in rec.getMessage()


def test_F_0_7_1_missing_db_url_is_a_clear_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.delenv("SFAC_DB_URL", raising=False)
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    with pytest.raises(RegistryError, match="SFAC_DB_URL is not set"):
        make_engine()
