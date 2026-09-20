"""F-0.6.1: split manager (20 % / 18 months, embargo), DataAccess dev-only, holdout lock."""

from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from fixtures.bars import make_meta
from fixtures.registry_db import RUN_CONFIG
from fixtures.t05 import MemoryLedger, bars_from_close, random_close
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine, func, select

from strategy_factory.core.errors import DataError, HoldoutAccessError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import SplitConfig, StalePriceConfig, load_quality_config
from strategy_factory.data.quality import check_snapshot
from strategy_factory.data.schema import SeriesMetadata
from strategy_factory.data.split import (
    HOLDOUT_STAGE,
    DataAccess,
    RegistryLedger,
    SplitManager,
    compute_split,
    subtract_months,
)
from strategy_factory.data.store import SnapshotStore

T0 = dt.datetime(2000, 1, 3, tzinfo=dt.UTC)


def daily(n: int, start: dt.datetime = T0) -> pl.DataFrame:
    return bars_from_close([start + dt.timedelta(days=i) for i in range(n)], random_close(n))


def stored(
    root: Path, df: pl.DataFrame, **meta: object
) -> tuple[SnapshotStore, Catalog, SeriesMetadata]:
    store, cat = SnapshotStore(root), Catalog(root)
    m = cat.register(store.write_snapshot(df, make_meta(**meta)))
    cat.set_reference(m.symbol, m.timeframe, m.snapshot_hash or "")
    return store, cat, m


def test_F_0_6_1_subtract_months() -> None:
    t = dt.datetime(2024, 8, 31, 5, tzinfo=dt.UTC)
    assert subtract_months(t, 18) == dt.datetime(2023, 2, 28, 5, tzinfo=dt.UTC)
    assert subtract_months(t, 1) == dt.datetime(2024, 7, 31, 5, tzinfo=dt.UTC)


def test_F_0_6_1_short_history_uses_18_month_minimum() -> None:
    df = daily(3 * 365)
    split = compute_split(df["ts"], make_meta(snapshot_hash="b" * 64).key(), SplitConfig())
    last = df["ts"][-1]
    assert split.holdout_start == subtract_months(last, 18)  # 20 % would be ~7 months
    assert split.holdout_end == last


def test_F_0_6_1_long_history_uses_20_percent() -> None:
    df = daily(20 * 365)
    split = compute_split(df["ts"], make_meta(snapshot_hash="b" * 64).key(), SplitConfig())
    first, last = df["ts"][0], df["ts"][-1]
    cutoff = last - 0.2 * (last - first)
    next_bar = cutoff.replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)
    assert split.holdout_start == next_bar  # first bar on or after the 20 % cutoff
    assert (split.holdout_end - split.holdout_start).days == pytest.approx(0.2 * 20 * 365, abs=2)


def test_F_0_6_1_embargo_applied() -> None:
    df = daily(3000)
    cfg = SplitConfig(max_lookback_bars=30, max_holding_bars=12)
    split = compute_split(df["ts"], make_meta(snapshot_hash="b" * 64).key(), cfg)
    ts = df["ts"].to_list()
    dev_end_i, hold_i = ts.index(split.dev_end), ts.index(split.holdout_start)
    assert split.embargo_bars == 42
    assert hold_i - dev_end_i - 1 == 42  # exactly 42 bars between development and holdout
    assert split.dev_start == ts[0]


def test_F_0_6_1_too_short_history_raises() -> None:
    with pytest.raises(DataError, match="history too short"):
        compute_split(daily(400)["ts"], make_meta(snapshot_hash="b" * 64).key(), SplitConfig())


def test_F_0_6_1_expected_trades_warning() -> None:
    key = make_meta(snapshot_hash="b" * 64).key()
    few = compute_split(daily(3 * 365)["ts"], key, SplitConfig(), trades_per_year=10)
    assert few.expected_holdout_trades == pytest.approx(15, abs=0.2)
    assert few.warnings and "< 30" in few.warnings[0]
    many = compute_split(daily(3 * 365)["ts"], key, SplitConfig(), trades_per_year=40)
    assert many.warnings == ()


def test_F_0_6_1_register_once_and_refuse_moved_boundaries(tmp_path: Path) -> None:
    store, cat, meta = stored(tmp_path, daily(3000))
    ledger = MemoryLedger()
    mgr = SplitManager(ledger, SplitConfig(), store, cat)
    first = mgr.compute("TEST", "1D", meta)
    assert ledger.snapshots == {meta.key(): True}
    assert mgr.compute("TEST", "1D", meta) == first  # idempotent
    other = SplitManager(ledger, SplitConfig(max_holding_bars=80), store, cat)
    with pytest.raises(DataError, match="already registered with other boundaries"):
        other.compute("TEST", "1D", meta)
    with pytest.raises(DataError, match="does not match"):
        mgr.compute("SPY", "1D", meta)


def test_F_0_6_1_data_access_dev_only_and_holdout_once(tmp_path: Path) -> None:
    store, cat, meta = stored(tmp_path, daily(3000))
    ledger = MemoryLedger()
    mgr = SplitManager(ledger, SplitConfig(), store, cat)
    access = DataAccess(mgr)
    dev = access.bars("TEST", "1D")
    split = access.split("TEST", "1D")
    assert dev["ts"].max() == split.dev_end and dev["ts"].min() == split.dev_start
    arrays = access.arrays("TEST", "1D")
    assert arrays["close"].shape == (dev.height,)
    hold = mgr.open_holdout("cand-1", "TEST", "1D", stage=HOLDOUT_STAGE)
    assert hold["ts"].min() == split.holdout_start and hold["ts"].max() == split.holdout_end
    assert ledger.accesses["cand-1"]["snapshot_hash"] == meta.snapshot_hash
    with pytest.raises(HoldoutAccessError):
        mgr.open_holdout("cand-1", "TEST", "1D", stage=HOLDOUT_STAGE)
    assert (
        mgr.open_holdout("cand-2", "TEST", "1D", stage=HOLDOUT_STAGE).height == hold.height
    )  # other candidate


def test_F_0_6_1_holdout_access_logged_before_reading(tmp_path: Path) -> None:
    store, cat, _ = stored(tmp_path, daily(3000))

    class Refusing(MemoryLedger):
        def record_holdout_access(self, candidate_id: str, result: dict) -> None:  # type: ignore[type-arg]
            raise HoldoutAccessError("registry down")

    mgr = SplitManager(Refusing(), SplitConfig(), store, cat)
    reads: list[str] = []
    orig = store.read_snapshot
    store.read_snapshot = lambda *a, **k: reads.append("read") or orig(*a, **k)  # type: ignore[method-assign]
    mgr.registered(cat.get_reference("TEST", "1D"))  # split exists; reads only ts
    reads.clear()
    with pytest.raises(HoldoutAccessError):
        mgr.open_holdout("c", "TEST", "1D", stage=HOLDOUT_STAGE)
    assert reads == []  # no bar was read when the access could not be recorded


def test_F_0_6_1_critical_quality_blocks_data_access(tmp_path: Path) -> None:
    df = daily(3000)
    close = df["close"].to_numpy().copy()
    close[100:110] = close[99]
    store, cat, meta = stored(tmp_path, bars_from_close(df["ts"].to_list(), close))
    strict = load_quality_config().model_copy(
        update={"stale_prices": StalePriceConfig(severity="critical")}
    )
    check_snapshot(meta, store, cat, strict)
    access = DataAccess(SplitManager(MemoryLedger(), SplitConfig(), store, cat))
    with pytest.raises(DataError, match="critical quality check"):
        access.bars("TEST", "1D")
    with pytest.raises(DataError, match="critical quality check"):
        access._splits.open_holdout("c", "TEST", "1D", stage=HOLDOUT_STAGE)


@settings(max_examples=30, deadline=None)
@given(
    n=st.integers(min_value=900, max_value=4000),
    fraction=st.floats(min_value=0.05, max_value=0.5),
    months=st.integers(min_value=1, max_value=24),
    lookback=st.integers(min_value=0, max_value=200),
    holding=st.integers(min_value=0, max_value=100),
    hours=st.booleans(),
)
def test_F_0_6_1_data_access_never_returns_holdout_rows(
    n: int, fraction: float, months: int, lookback: int, holding: int, hours: bool
) -> None:
    step = dt.timedelta(hours=1) if hours else dt.timedelta(days=1)
    df = bars_from_close([T0 + i * step for i in range(n)], random_close(n))
    cfg = SplitConfig(
        holdout_fraction=fraction,
        holdout_min_months=months,
        max_lookback_bars=lookback,
        max_holding_bars=holding,
    )
    with tempfile.TemporaryDirectory() as tmp:
        store, cat, _ = stored(Path(tmp), df, timeframe="1H" if hours else "1D")
        mgr = SplitManager(MemoryLedger(), cfg, store, cat)
        access = DataAccess(mgr)
        tf = "1H" if hours else "1D"
        try:
            dev = access.bars("TEST", tf)
        except DataError as exc:
            assert "history too short" in str(exc)
            return
        split = access.split("TEST", tf)
        hold = mgr.open_holdout("c", "TEST", tf, stage=HOLDOUT_STAGE)
    assert dev["ts"].max() < split.holdout_start
    assert not set(dev["ts"].to_list()) & set(hold["ts"].to_list())
    assert dev.height + split.embargo_bars + hold.height == n
    assert hold["ts"].min() >= subtract_months(df["ts"][-1], months) or (
        hold["ts"].min() >= df["ts"][-1] - fraction * (df["ts"][-1] - df["ts"][0])
    )


# -- registry (PostgreSQL) -----------------------------------------------------------------
@pytest.mark.db
def test_F_0_6_1_split_registered_and_second_holdout_access_raises(
    tmp_path: Path, registry_engine: Engine, second_engine: Engine
) -> None:
    from strategy_factory.registry.tables import data_snapshots, holdout_access, splits

    store, cat, meta = stored(tmp_path, daily(3000))
    mgr = SplitManager(RegistryLedger(registry_engine), SplitConfig(), store, cat)
    split = mgr.compute("TEST", "1D", meta, trades_per_year=12)
    with registry_engine.connect() as conn:
        row = conn.execute(select(splits)).one()._mapping
        snap = conn.execute(select(data_snapshots)).one()._mapping
    assert (row["snapshot_hash"], row["source"], row["symbol"], row["timeframe"]) == (
        meta.snapshot_hash,
        "test",
        "TEST",
        "1D",
    )
    assert row["dev_end"] == split.dev_end and row["holdout_start"] == split.holdout_start
    years = (split.holdout_end - split.holdout_start) / dt.timedelta(days=365.25)
    assert years > 1.5  # 3000 days: 20 % (~1.64 years) beats the 18-month minimum
    assert row["embargo_bars"] == 250
    assert row["expected_holdout_trades"] == pytest.approx(12 * years)
    assert snap["is_reference"] is True
    assert mgr.compute("TEST", "1D", meta) == split.model_copy(
        update={"expected_holdout_trades": None, "warnings": ()}
    )  # idempotent: no second row

    from strategy_factory.registry.writer import CandidateRecord, RegistryWriter

    w = RegistryWriter(registry_engine)
    run_id = w.start_run(RUN_CONFIG, seed=1, code_version="c" * 40)
    w.upsert_candidate(
        CandidateRecord(
            id="cand-1",
            run_id=run_id,
            symbol="TEST",
            timeframe="1D",
            direction="long",
            edge_type="MR",
            spec={},
            spec_hash="h",
            current_stage="s06",
        )
    )
    hold = mgr.open_holdout("cand-1", "TEST", "1D", stage=HOLDOUT_STAGE)
    assert hold["ts"].min() == split.holdout_start
    with pytest.raises(HoldoutAccessError):
        mgr.open_holdout("cand-1", "TEST", "1D", stage=HOLDOUT_STAGE)
    other_process = SplitManager(RegistryLedger(second_engine), SplitConfig(), store, cat)
    with pytest.raises(HoldoutAccessError):
        other_process.open_holdout("cand-1", "TEST", "1D", stage=HOLDOUT_STAGE)
    with registry_engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(holdout_access)).scalar_one() == 1
        assert conn.execute(select(func.count()).select_from(splits)).scalar_one() == 1
    dev = DataAccess(other_process).bars("TEST", "1D")
    assert dev["ts"].max() == split.dev_end
    assert np.all(dev["ts"].to_numpy() < np.datetime64(split.holdout_start.replace(tzinfo=None)))
