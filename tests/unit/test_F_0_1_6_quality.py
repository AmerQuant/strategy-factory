"""F-0.1.6: data-quality checks, report files, catalog status and the critical block."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from fixtures.bars import make_bars, make_meta
from fixtures.t05 import (
    FAKE_HASH,
    NY,
    bars_from_close,
    fx_bars,
    fx_hours,
    fx_meta,
    random_close,
)
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.core.errors import DataError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.cli_prep import summary_frame
from strategy_factory.data.config import QualityConfig, StalePriceConfig
from strategy_factory.data.quality import (
    QUALITY_DIR,
    check_snapshot,
    ensure_usable,
    run_quality,
)
from strategy_factory.data.store import SnapshotStore

CFG = QualityConfig()
W0 = dt.datetime(2024, 1, 7, 22, tzinfo=dt.UTC)  # Sunday 17:00 New York (winter)
W1 = dt.datetime(2024, 3, 1, 21, tzinfo=dt.UTC)  # Friday 16:00 New York


def failed(rep) -> set[str]:  # type: ignore[no-untyped-def]
    return {c.code for c in rep.failed()}


def test_F_0_1_6_clean_snapshot_is_ok() -> None:
    rep = run_quality(fx_bars(W0, W1, break_hour_ny=17), fx_meta(), CFG)
    assert rep.status == "ok"
    assert failed(rep) == set()
    assert rep.check("dst").status == "skipped"  # UTC source
    assert rep.schedule["break_hour_local"] == 17
    assert rep.schedule["modal_break_hour_utc"] == 22  # winter: 17:00 New York = 22:00 UTC


def test_F_0_1_6_break_learned_in_local_time_across_dst() -> None:
    df = fx_bars(
        dt.datetime(2024, 2, 4, 22, tzinfo=dt.UTC), dt.datetime(2024, 4, 26, 20, tzinfo=dt.UTC), 17
    )
    rep = run_quality(df, fx_meta(), CFG)
    assert rep.schedule["break_hour_local"] == 17  # 22:00 UTC in winter, 21:00 UTC in summer
    assert failed(rep) == set()


def test_F_0_1_6_no_break_for_continuous_market() -> None:
    rep = run_quality(fx_bars(W0, W1), fx_meta(), CFG)
    assert rep.schedule["break_hour_local"] is None
    assert rep.status == "ok"


def test_F_0_1_6_missing_bars_warning_above_threshold_info_below() -> None:
    df = fx_bars(W0, W1, 17)
    many = df.filter(pl.col("ts").dt.date() != dt.date(2024, 1, 17))  # a whole UTC day (~2.5 %)
    rep = run_quality(many, fx_meta(), CFG)
    assert failed(rep) == {"missing_bars"}
    miss = rep.check("missing_bars")
    assert miss.severity == "warning" and miss.details["pct"] > 2.0
    assert miss.count == 23  # 24 hours minus the break hour (22:00 UTC in winter)
    assert rep.status == "warning"

    few = df.filter(pl.col("ts") != dt.datetime(2024, 1, 17, 10, tzinfo=dt.UTC))
    rep = run_quality(few, fx_meta(), CFG)
    assert failed(rep) == {"missing_bars"}
    assert rep.check("missing_bars").severity == "info"
    assert rep.status == "ok"  # info does not raise the status


def test_F_0_1_6_session_violation() -> None:
    df = fx_bars(W0, W1, 17)
    saturday = bars_from_close([dt.datetime(2024, 1, 13, 12, tzinfo=dt.UTC)], np.array([100.0]))
    rep = run_quality(pl.concat([df, saturday]).sort("ts"), fx_meta(), CFG)
    assert failed(rep) == {"session_violations"}
    assert rep.check("session_violations").count == 1


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda d: pl.concat([d, d.slice(10, 1)]), "ts_duplicate"),
        (
            lambda d: d.with_columns(
                high=pl.when(pl.int_range(pl.len()) == 5).then(0.5).otherwise(pl.col("high"))
            ),
            "high_lt_low",
        ),
        (
            lambda d: d.with_columns(
                low=pl.when(pl.int_range(pl.len()) == 7).then(-1.0).otherwise(pl.col("low"))
            ),
            "nonpositive_price",
        ),
    ],
)
def test_F_0_1_6_schema_errors_are_critical(mutate, code) -> None:  # type: ignore[no-untyped-def]
    rep = run_quality(mutate(fx_bars(W0, W1, 17)).sort("ts"), fx_meta(), CFG)
    assert "schema" in failed(rep)
    schema = rep.check("schema")
    assert schema.severity == "critical" and code in schema.details["issues"]
    assert rep.status == "critical"


def test_F_0_1_6_price_spike_with_reversal() -> None:
    df = fx_bars(W0, W1, 17)
    i = 300
    close = df["close"].to_numpy().copy()
    close[i] *= 1.05  # +5 % on one bar, back on the next
    rep = run_quality(bars_from_close(df["ts"].to_list(), close), fx_meta(), CFG)
    assert failed(rep) == {"price_spikes"}
    spikes = rep.check("price_spikes")
    assert spikes.count == 1 and spikes.details["bars"] == [df["ts"][i].isoformat()]


def test_F_0_1_6_level_shift_without_reversal_is_not_a_spike() -> None:
    df = fx_bars(W0, W1, 17)
    close = df["close"].to_numpy().copy()
    close[300:] *= 1.05  # a real jump that stays
    rep = run_quality(bars_from_close(df["ts"].to_list(), close), fx_meta(), CFG)
    assert "price_spikes" not in failed(rep)


def test_F_0_1_6_stale_prices() -> None:
    df = fx_bars(W0, W1, 17)
    close = df["close"].to_numpy().copy()
    close[200:206] = close[199]  # open = previous close -> bars 200..205 identical OHLC
    bars = bars_from_close(df["ts"].to_list(), close)
    rep = run_quality(bars, fx_meta(), CFG)
    assert failed(rep) == {"stale_prices"}
    stale = rep.check("stale_prices")
    assert stale.count == 1 and stale.details["longest"] == 6
    assert stale.details["runs_from"] == [df["ts"][200].isoformat()]


def test_F_0_1_6_zero_volume() -> None:
    df = fx_bars(W0, W1, 17)
    zeroed = df.with_columns(
        volume=pl.when(pl.int_range(pl.len()) % 10 == 0).then(0.0).otherwise(pl.col("volume"))
    )
    rep = run_quality(zeroed, fx_meta(), CFG)
    assert failed(rep) == {"zero_volume"}
    assert rep.check("zero_volume").severity == "warning"  # 10 % > 5 %
    rep = run_quality(zeroed, fx_meta(volume_quality="none"), CFG)
    assert rep.check("zero_volume").status == "skipped"
    assert failed(rep) == set()


def _exchange_local_hours(wrong: bool) -> list[dt.datetime]:
    """Hourly bars 09:00-15:00 New York around the March 2024 DST change."""
    out = []
    day = dt.date(2024, 2, 26)
    while day <= dt.date(2024, 3, 22):
        if day.isoweekday() <= 5:
            for h in range(9, 16):
                if wrong:  # converted with a fixed winter offset (UTC-5) all year
                    out.append(dt.datetime.combine(day, dt.time(h + 5), tzinfo=dt.UTC))
                else:
                    local = dt.datetime.combine(day, dt.time(h), tzinfo=NY)
                    out.append(local.astimezone(dt.UTC))
        day += dt.timedelta(days=1)
    return out


def test_F_0_1_6_dst_discontinuity_only_for_exchange_local_sources() -> None:
    meta = make_meta(
        asset_class="futures",
        timeframe="1H",
        original_tz="America/New_York",
        session="exchange",
        adjustment="back_adjusted",
        feed="none",
        snapshot_hash=FAKE_HASH,
    )
    good = _exchange_local_hours(wrong=False)
    rep = run_quality(bars_from_close(good, random_close(len(good))), meta, CFG)
    assert rep.check("dst").status == "pass"
    assert failed(rep) == set()

    bad = _exchange_local_hours(wrong=True)
    rep = run_quality(bars_from_close(bad, random_close(len(bad))), meta, CFG)
    assert failed(rep) == {"dst"}
    assert "2024-03-10" in rep.check("dst").details["transitions"][0]

    utc_meta = meta.model_copy(update={"original_tz": "UTC"})
    assert (
        run_quality(bars_from_close(bad, random_close(len(bad))), utc_meta, CFG).check("dst").status
        == "skipped"
    )


def test_F_0_1_6_us_equity_schedule_from_sessions_file(tmp_path: Path) -> None:
    sessions = tmp_path / "nyse_sessions.csv"
    sessions.write_text(
        "date,open_local,close_local\n2024-07-02,09:30,16:00\n2024-07-03,09:30,13:00\n"
        "2024-07-05,09:30,16:00\n",
        encoding="utf-8",
    )
    ts = []
    for day, close in (
        (dt.date(2024, 7, 2), 16),
        (dt.date(2024, 7, 3), 13),
        (dt.date(2024, 7, 5), 16),
    ):
        ts += [
            dt.datetime.combine(day, dt.time(h), tzinfo=NY).astimezone(dt.UTC)
            for h in range(9, close)
        ]
    meta = make_meta(
        timeframe="1H", session="RTH_hour_aligned", original_tz="UTC", snapshot_hash=FAKE_HASH
    )
    rep = run_quality(bars_from_close(ts, random_close(len(ts))), meta, CFG, sessions)
    assert failed(rep) == set(), rep.checks
    assert rep.check("missing_bars").details["expected"] == 7 + 4 + 7  # early close 13:00

    late = [*ts, dt.datetime(2024, 7, 3, 13, tzinfo=NY).astimezone(dt.UTC)]  # after early close
    rep = run_quality(bars_from_close(sorted(late), random_close(len(late))), meta, CFG, sessions)
    assert failed(rep) == {"session_violations"}

    no_file = run_quality(bars_from_close(ts, random_close(len(ts))), meta, CFG, tmp_path / "x.csv")
    assert no_file.check("missing_bars").status == "skipped"
    assert "calendar not found" in no_file.check("missing_bars").message


# -- store / catalog / gate ---------------------------------------------------------------
@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "store"
    monkeypatch.setenv("SFAC_DATA_ROOT", str(root))
    monkeypatch.chdir(tmp_path)
    return root


def test_F_0_1_6_report_files_and_catalog_status(data_root: Path) -> None:
    store, cat = SnapshotStore(), Catalog()
    meta = cat.register(store.write_snapshot(fx_bars(W0, W1, 17), fx_meta()))
    assert cat.quality_status(meta.key()) == "unchecked"
    rep = check_snapshot(meta, store, cat, CFG)
    assert rep.status == "ok"
    assert cat.quality_status(meta.key()) == "ok"
    js = data_root / QUALITY_DIR / f"{meta.snapshot_hash}.json"
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["status"] == "ok" and data["snapshot"]["symbol"] == "EURUSD"
    assert {c["code"] for c in data["checks"]} == {
        "schema",
        "missing_bars",
        "session_violations",
        "price_spikes",
        "stale_prices",
        "zero_volume",
        "dst",
        # T04k adds two daily checks; both are skipped on this 1H fx snapshot
        "daily_wick_outlier",
        "daily_extreme_unsupported",
        # T04l (D-709): read from the catalog marker; passes on an unmarked snapshot
        "known_splice",
    }
    assert "status: **ok**" in js.with_suffix(".md").read_text(encoding="utf-8")
    assert cat.events()["event"].to_list()[-1] == "quality"
    assert ensure_usable(cat, meta.key()) == "ok"


def test_F_0_1_6_critical_status_blocks_use(data_root: Path) -> None:
    df = fx_bars(W0, W1, 17)
    close = df["close"].to_numpy().copy()
    close[100:110] = close[99]
    store, cat = SnapshotStore(), Catalog()
    meta = cat.register(store.write_snapshot(bars_from_close(df["ts"].to_list(), close), fx_meta()))
    strict = CFG.model_copy(update={"stale_prices": StalePriceConfig(severity="critical")})
    assert check_snapshot(meta, store, cat, strict).status == "critical"
    with pytest.raises(DataError, match="critical quality check"):
        ensure_usable(cat, meta.key())


def test_F_0_1_6_old_catalog_rows_are_unchecked(data_root: Path) -> None:
    cat = Catalog()
    meta = cat.register(SnapshotStore().write_snapshot(make_bars(5), make_meta()))
    old = pl.read_parquet(cat.path).drop("quality_status", "derived_from")
    old.write_parquet(cat.path)  # a catalog written before T05
    assert cat.quality_status(meta.key()) == "unchecked"
    assert cat.get(meta.key()).derived_from is None


def test_F_0_1_6_cli_quality_all(data_root: Path) -> None:
    store, cat = SnapshotStore(), Catalog()
    cat.register(store.write_snapshot(fx_bars(W0, W1, 17), fx_meta()))
    cat.register(store.write_snapshot(make_bars(20), make_meta()))  # us_equity, no calendar
    runner = CliRunner()
    assert runner.invoke(app, ["data", "quality"]).exit_code == 1  # needs --symbol or --all
    res = runner.invoke(app, ["data", "quality", "--all"])
    assert res.exit_code == 0, res.output
    assert "2 snapshot(s)" in res.output and "EURUSD" in res.output
    assert (data_root / QUALITY_DIR / "summary.md").is_file()
    assert set(cat.table()["quality_status"].to_list()) == {"ok"}
    listed = runner.invoke(app, ["data", "list"])
    assert "quality_status" in listed.output


def test_F_0_1_6_fx_hours_helper_matches_week_window() -> None:
    hours = fx_hours(W0, W0 + dt.timedelta(days=7))
    assert hours[0] == W0 and all(h.astimezone(NY).isoweekday() != 6 for h in hours)


# --- D-391: one summary per (source, timeframe) plus an index -------------------------------


def test_F_0_1_6_D_391_one_summary_per_source_and_timeframe(data_root: Path) -> None:
    store, cat = SnapshotStore(), Catalog()
    cat.register(store.write_snapshot(fx_bars(W0, W1, 17), fx_meta()))
    cat.register(store.write_snapshot(make_bars(20), make_meta()))
    assert CliRunner().invoke(app, ["data", "quality", "--all"]).exit_code == 0
    q = data_root / QUALITY_DIR
    assert (q / "summary_dukascopy_1H.md").is_file()
    assert (q / "summary_test_1D.md").is_file()
    assert "EURUSD" in (q / "summary_dukascopy_1H.md").read_text(encoding="utf-8")
    assert "EURUSD" not in (q / "summary_test_1D.md").read_text(encoding="utf-8")


def test_F_0_1_6_D_391_the_index_lists_every_group_with_its_counts(data_root: Path) -> None:
    store, cat = SnapshotStore(), Catalog()
    cat.register(store.write_snapshot(fx_bars(W0, W1, 17), fx_meta()))
    cat.register(store.write_snapshot(make_bars(20), make_meta()))
    assert CliRunner().invoke(app, ["data", "quality", "--all"]).exit_code == 0
    index = (data_root / QUALITY_DIR / "summary.md").read_text(encoding="utf-8")
    assert "summary_dukascopy_1H.md" in index and "summary_test_1D.md" in index
    assert "| dukascopy | 1H | 1 |" in index
    assert "| test | 1D | 1 |" in index


def test_F_0_1_6_D_391_a_partial_run_rewrites_only_its_own_group(data_root: Path) -> None:
    """A run that touches one group leaves the other group's file alone but refreshes the index."""
    store, cat = SnapshotStore(), Catalog()
    cat.register(store.write_snapshot(fx_bars(W0, W1, 17), fx_meta()))
    cat.register(store.write_snapshot(make_bars(20), make_meta()))
    runner = CliRunner()
    assert runner.invoke(app, ["data", "quality", "--all"]).exit_code == 0
    q = data_root / QUALITY_DIR
    other = q / "summary_dukascopy_1H.md"
    other.write_text("MARKER\n", encoding="utf-8")
    (q / "summary.md").unlink()
    assert runner.invoke(app, ["data", "quality", "--symbol", "TEST"]).exit_code == 0
    assert other.read_text(encoding="utf-8") == "MARKER\n"  # untouched group
    index = (q / "summary.md").read_text(encoding="utf-8")
    assert "summary_dukascopy_1H.md" in index  # the index still knows about it


def test_F_0_1_6_D_391_a_large_run_does_not_print_every_row(data_root: Path) -> None:
    """6,711 daily snapshots must not dump 6,711 lines to the console (T04g)."""
    store, cat = SnapshotStore(), Catalog()
    for i in range(6):
        meta = make_meta(symbol=f"SYM{i}")
        cat.register(store.write_snapshot(make_bars(20 + i), meta))
    res = CliRunner().invoke(app, ["data", "quality", "--all", "--max-rows", "3"])
    assert res.exit_code == 0, res.output
    assert "SYM0" in res.output and "SYM5" not in res.output
    assert "6 snapshot(s)" in res.output


def test_F_0_1_6_T04g_the_summary_survives_a_late_first_break_hour() -> None:
    """A schedule field that is null past row 100 and an hour afterwards must not raise.

    Measured in T04g: over 6,707 daily snapshots `pl.DataFrame(out)` inferred `break_local` as
    null from the first 100 rows and then failed with
    `ComputeError: could not append value: 17 of type: i64` on the first intraday snapshot.
    120 rows, so the default `infer_schema_length=100` would not see the hour.
    """
    rows: list[dict[str, object]] = [
        {"symbol": f"EQ{i}", "status": "ok", "break_local": None, "break_utc": None}
        for i in range(119)
    ]
    rows.append({"symbol": "EURUSD", "status": "ok", "break_local": 17, "break_utc": 22})
    with pytest.raises(Exception, match="could not append value"):
        pl.DataFrame(rows)  # the default infer_schema_length=100 is what failed
    frame = summary_frame(rows)
    assert frame.height == 120
    assert frame["break_local"].to_list()[-1] == 17
