"""F-0.1.7: resampling, day boundary, Sunday merge, broker_session alignment, lineage."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from fixtures.bars import make_meta
from fixtures.t05 import (
    FAKE_HASH,
    NY,
    bars_from_close,
    crypto_meta,
    fx_bars,
    fx_meta,
    hourly,
    random_close,
)
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.core.errors import DataError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import QualityConfig, ResampleConfig
from strategy_factory.data.resample import flags_file, resample, resample_bars
from strategy_factory.data.store import SnapshotStore

CFG, QCFG = ResampleConfig(), QualityConfig()
D0 = dt.datetime(2024, 3, 4, tzinfo=dt.UTC)  # Monday 00:00 UTC


def test_F_0_1_7_hand_computed_1h_to_1d() -> None:
    ts = hourly(D0, 48)
    close = np.arange(1.0, 49.0) + 100
    df = bars_from_close(ts, close)
    out = resample_bars(df, crypto_meta(), "1D", "research", CFG, QCFG).bars
    assert out["ts"].to_list() == [D0, D0 + dt.timedelta(days=1)]
    for day, sl in enumerate((slice(0, 24), slice(24, 48))):
        part = df[sl]
        row = out.row(day, named=True)
        assert row["open"] == part["open"][0]
        assert row["high"] == part["high"].max()
        assert row["low"] == part["low"].min()
        assert row["close"] == part["close"][-1]
        assert row["volume"] == pytest.approx(part["volume"].sum())
    assert out["volume"].sum() == pytest.approx(df["volume"].sum())


def test_F_0_1_7_sunday_merged_into_monday() -> None:
    # Sunday 22:00 UTC (17:00 New York, winter) .. Friday 21:00 UTC, no break
    start = dt.datetime(2024, 1, 7, 22, tzinfo=dt.UTC)
    df = fx_bars(start, dt.datetime(2024, 1, 19, 21, tzinfo=dt.UTC))
    out = resample_bars(df, fx_meta(), "1D", "research", CFG, QCFG)
    days = out.bars["ts"]
    assert set(days.dt.weekday().to_list()) <= {1, 2, 3, 4, 5}  # never Saturday/Sunday
    monday = out.bars.filter(pl.col("ts") == dt.datetime(2024, 1, 8, tzinfo=dt.UTC)).row(
        0, named=True
    )
    src = df.filter(
        (pl.col("ts") >= start) & (pl.col("ts") < dt.datetime(2024, 1, 9, tzinfo=dt.UTC))
    )
    assert src.height == 2 + 24  # Sunday evening 22:00, 23:00 + Monday
    assert monday["open"] == src["open"][0]  # the Sunday 22:00 open
    assert monday["close"] == src["close"][-1]
    assert monday["volume"] == pytest.approx(src["volume"].sum())
    assert monday["high"] == src["high"].max() and monday["low"] == src["low"].min()


def test_F_0_1_7_saturday_bars_also_go_to_monday() -> None:
    df = bars_from_close(
        [dt.datetime(2024, 1, 13, 10, tzinfo=dt.UTC), dt.datetime(2024, 1, 15, 10, tzinfo=dt.UTC)],
        np.array([1.0, 2.0]),
    )
    out = resample_bars(df, fx_meta(), "1D", "research", CFG, QCFG)
    assert not set(out.bars["ts"].dt.weekday().to_list()) & {6, 7}


def test_F_0_1_7_1h_to_4h_fixed_utc_blocks() -> None:
    df = bars_from_close(hourly(D0, 24), random_close(24))
    out = resample_bars(df, crypto_meta(), "4H", "research", CFG, QCFG).bars
    assert out["ts"].dt.hour().to_list() == [0, 4, 8, 12, 16, 20]
    blk = df.slice(8, 4)
    row = out.row(2, named=True)
    assert (row["open"], row["close"]) == (blk["open"][0], blk["close"][-1])
    assert row["high"] == blk["high"].max() and row["low"] == blk["low"].min()


def test_F_0_1_7_us_equity_4h_and_daily_rejected() -> None:
    meta = make_meta(timeframe="1H", session="RTH_hour_aligned", snapshot_hash=FAKE_HASH)
    df = bars_from_close(hourly(D0 + dt.timedelta(hours=14), 7), random_close(7))
    with pytest.raises(DataError, match="4H bars are built only for 24-hour markets"):
        resample_bars(df, meta, "4H", "research", CFG, QCFG)
    with pytest.raises(DataError, match="Alpaca daily snapshots"):
        resample_bars(df, meta, "1D", "research", CFG, QCFG)
    futures = make_meta(asset_class="futures", timeframe="1H", snapshot_hash=FAKE_HASH)
    with pytest.raises(DataError, match="only for 24-hour markets"):
        resample_bars(df, futures, "4H", "research", CFG, QCFG)
    with pytest.raises(DataError, match="coarser multiple"):
        resample_bars(df, crypto_meta(timeframe="4H"), "1H", "research", CFG, QCFG)


@pytest.mark.parametrize(
    ("week_start", "session_open_utc"),
    [
        (dt.datetime(2024, 1, 7, 22, tzinfo=dt.UTC), 22),  # winter: 17:00 New York = 22:00 UTC
        (dt.datetime(2024, 6, 9, 21, tzinfo=dt.UTC), 21),  # summer: 17:00 New York = 21:00 UTC
    ],
)
def test_F_0_1_7_broker_session_alignment(week_start: dt.datetime, session_open_utc: int) -> None:
    df = fx_bars(week_start, week_start + dt.timedelta(days=12))
    res = resample_bars(df, fx_meta(), "1D", "broker_session", CFG, QCFG)
    first = res.bars.row(0, named=True)
    monday = week_start.date() + dt.timedelta(days=1)
    assert first["ts"] == dt.datetime.combine(monday, dt.time(0), tzinfo=dt.UTC)
    session = df.filter(
        (pl.col("ts") >= week_start) & (pl.col("ts") < week_start + dt.timedelta(days=1))
    )
    assert session["ts"][0].hour == session_open_utc
    assert first["open"] == session["open"][0] and first["close"] == session["close"][-1]
    assert first["volume"] == pytest.approx(session["volume"].sum())
    local_starts = session["ts"].dt.convert_time_zone("America/New_York")
    assert local_starts[0].hour == 17 and local_starts[-1].hour == 16
    assert set(res.bars["ts"].dt.weekday().to_list()) <= {1, 2, 3, 4, 5}


def test_F_0_1_7_broker_session_4h_blocks_follow_session_start() -> None:
    week_start = dt.datetime(2024, 1, 7, 22, tzinfo=dt.UTC)
    df = fx_bars(week_start, week_start + dt.timedelta(days=4))
    out = resample_bars(df, fx_meta(), "4H", "broker_session", CFG, QCFG).bars
    local_hours = set(out["ts"].dt.convert_time_zone("America/New_York").dt.hour().to_list())
    assert local_hours == {17, 21, 1, 5, 9, 13}


def test_F_0_1_7_partial_periods_dropped() -> None:
    df = bars_from_close(hourly(D0 + dt.timedelta(hours=5), 24 * 3), random_close(72))
    res = resample_bars(df, crypto_meta(), "1D", "research", CFG, QCFG)
    # starts Mon 05:00 (Mon partial) and ends Thu 04:00 (Thu partial) -> Tue, Wed only
    assert res.bars["ts"].to_list() == [D0 + dt.timedelta(days=1), D0 + dt.timedelta(days=2)]
    assert len(res.dropped) == 2
    full = bars_from_close(hourly(D0, 48), random_close(48))
    assert resample_bars(full, crypto_meta(), "1D", "research", CFG, QCFG).dropped == ()


def test_F_0_1_7_bars_with_few_source_bars_are_flagged() -> None:
    df = fx_bars(
        dt.datetime(2024, 1, 7, 22, tzinfo=dt.UTC), dt.datetime(2024, 1, 19, 21, tzinfo=dt.UTC)
    )
    holiday = df.filter(
        (pl.col("ts").dt.date() != dt.date(2024, 1, 10)) | (pl.col("ts").dt.hour() < 6)
    )  # only 6 of 24 bars on Wednesday
    res = resample_bars(holiday, fx_meta(), "1D", "research", CFG, QCFG)
    assert res.flags.rows() == [(dt.datetime(2024, 1, 10, tzinfo=dt.UTC), 6, 24)]


def test_F_0_1_7_vwap_trades_spread() -> None:
    n = 24
    df = bars_from_close(
        hourly(D0, n),
        random_close(n),
        vwap=np.linspace(10.0, 20.0, n),
        trades=np.arange(n, dtype=np.int64),
        spread=np.linspace(0.1, 0.3, n),
    ).with_columns(volume=pl.Series(np.arange(1.0, n + 1)))
    row = resample_bars(df, crypto_meta(), "1D", "research", CFG, QCFG).bars.row(0, named=True)
    v, w = df["vwap"].to_numpy(), df["volume"].to_numpy()
    assert row["vwap"] == pytest.approx(float((v * w).sum() / w.sum()))
    assert row["vwap"] != pytest.approx(float(v.mean()))  # weighted, not a plain mean
    assert row["trades"] == int(df["trades"].sum())
    assert row["spread"] == df["spread"][-1]


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "store"
    monkeypatch.setenv("SFAC_DATA_ROOT", str(root))
    monkeypatch.chdir(tmp_path)
    return root


def test_F_0_1_7_lineage_metadata_and_store(data_root: Path) -> None:
    store, cat = SnapshotStore(), Catalog()
    df = fx_bars(
        dt.datetime(2024, 1, 7, 22, tzinfo=dt.UTC), dt.datetime(2024, 1, 26, 21, tzinfo=dt.UTC), 17
    )
    parent = cat.register(store.write_snapshot(df, fx_meta()))
    child, res = resample(parent, "1D", store=store, catalog=cat, cfg=CFG, qcfg=QCFG)
    assert child.timeframe == "1D" and child.is_stored
    assert child.derived_from == parent.key()
    assert "resampled 1H->1D mode=research" in child.notes
    assert "Sat/Sun merged into Monday" in child.notes
    assert child.raw_refs == parent.raw_refs
    again = cat.get(child.key())
    assert again.derived_from == parent.key() and again.notes == child.notes
    assert (
        store.read_metadata("dukascopy", "EURUSD", "1D", child.snapshot_hash or "").derived_from
        == parent.key()
    )
    assert flags_file(data_root, child.snapshot_hash or "").is_file()
    assert res.break_hour_local == 17


def test_F_0_1_7_cli_resample(data_root: Path) -> None:
    store, cat = SnapshotStore(), Catalog()
    df = fx_bars(
        dt.datetime(2024, 1, 7, 22, tzinfo=dt.UTC), dt.datetime(2024, 1, 26, 21, tzinfo=dt.UTC)
    )
    parent = cat.register(store.write_snapshot(df, fx_meta()))
    cat.set_reference("EURUSD", "1H", parent.snapshot_hash or "")
    runner = CliRunner()
    res = runner.invoke(
        app, ["data", "resample", "--symbol", "EURUSD", "--from", "1H", "--to", "4H"]
    )
    assert res.exit_code == 0, res.output
    assert "(reference)" in res.output
    assert cat.get_reference("EURUSD", "4H").derived_from == parent.key()
    broker = runner.invoke(
        app,
        [
            "data",
            "resample",
            "--symbol",
            "EURUSD",
            "--from",
            "1H",
            "--to",
            "1D",
            "--mode",
            "broker_session",
        ],
    )
    assert broker.exit_code == 0, broker.output
    assert not cat.has_reference("EURUSD", "1D")  # broker_session never becomes the reference
    bad = runner.invoke(
        app,
        [
            "data",
            "resample",
            "--symbol",
            "EURUSD",
            "--from",
            "1H",
            "--to",
            "1D",
            "--mode",
            "broker_session",
            "--set-reference",
        ],
    )
    assert bad.exit_code == 1


def test_F_0_1_7_broker_mode_note_parsed_by_quality(data_root: Path) -> None:
    from strategy_factory.data.quality import check_snapshot

    store, cat = SnapshotStore(), Catalog()
    df = fx_bars(
        dt.datetime(2024, 1, 7, 22, tzinfo=dt.UTC), dt.datetime(2024, 1, 26, 21, tzinfo=dt.UTC)
    )
    parent = cat.register(store.write_snapshot(df, fx_meta()))
    child, _ = resample(
        parent, "1D", "broker_session", store=store, catalog=cat, cfg=CFG, qcfg=QCFG
    )
    rep = check_snapshot(child, store, cat, QCFG)
    assert {c.code for c in rep.failed()} == set(), rep.checks
    assert NY.key == "America/New_York"
