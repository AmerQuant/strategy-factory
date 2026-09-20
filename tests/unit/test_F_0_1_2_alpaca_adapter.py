"""F-0.1.2: Alpaca adapter -- stamps, session filter, metadata, duplicate chunks, ingest."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
import pytest
from fixtures.alpaca_helpers import load_fixture, make_config
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.core.errors import DataError
from strategy_factory.data.adapters.alpaca import AlpacaAdapter
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.download.alpaca import latest_chunks, write_chunk
from strategy_factory.data.ingest import ingest_alpaca_symbol
from strategy_factory.data.schema import validate_bars
from strategy_factory.data.store import SnapshotStore

REQ = {"feed": "sip", "adjustment": "split"}
NY = "America/New_York"


def raw_file(tmp_path: Path, tf: str, symbol: str, year: int, fixture: str) -> list[Path]:
    rows = load_fixture(fixture)[symbol]
    write_chunk(tmp_path, tf, symbol, year, rows, REQ, True, "fake 0")
    return latest_chunks(tmp_path, tf, symbol)


@pytest.fixture
def adapter() -> AlpacaAdapter:
    return AlpacaAdapter(make_config())


def test_F_0_1_2_daily_stamp_is_session_date_across_dst(
    tmp_path: Path, adapter: AlpacaAdapter
) -> None:
    files = raw_file(tmp_path, "1D", "AAPL", 2020, "daily_2020.json")
    raw = pl.read_parquet(files[0])
    # Alpaca stamps: midnight New York = 04:00 UTC (EDT) and 05:00 UTC (EST)
    assert "2020-10-30T04:00:00Z" in raw["t"].to_list()
    assert "2020-11-02T05:00:00Z" in raw["t"].to_list()
    df, meta = adapter.to_canonical(files, timeframe="1D", symbol="AAPL")
    ts = df["ts"].to_list()
    assert dt.datetime(2020, 10, 30, tzinfo=dt.UTC) in ts
    assert dt.datetime(2020, 11, 2, tzinfo=dt.UTC) in ts
    assert all(t.hour == 0 and t.minute == 0 for t in ts)
    assert validate_bars(df, meta) == []


def test_F_0_1_2_hourly_keeps_0900_to_1500_ny_on_both_sides_of_dst(
    tmp_path: Path, adapter: AlpacaAdapter
) -> None:
    files = raw_file(tmp_path, "1H", "AAPL", 2024, "hourly_2024.json")
    df, meta = adapter.to_canonical(files, timeframe="1H", symbol="AAPL")
    ny = df.with_columns(pl.col("ts").dt.convert_time_zone(NY).alias("ny"))
    per_day = ny.group_by(pl.col("ny").dt.date().alias("d")).agg(
        pl.len().alias("n"),
        pl.col("ny").dt.hour().min().alias("first"),
        pl.col("ny").dt.hour().max().alias("last"),
    )
    rows = {r["d"]: r for r in per_day.iter_rows(named=True)}
    for d in (dt.date(2024, 3, 8), dt.date(2024, 3, 11)):  # EST, then EDT
        assert (rows[d]["n"], rows[d]["first"], rows[d]["last"]) == (7, 9, 15)
    # same NY label, different UTC hour across the DST switch
    firsts = ny.group_by(pl.col("ny").dt.date().alias("d")).agg(pl.col("ts").min())
    utc_first = {r["d"]: r["ts"].hour for r in firsts.iter_rows(named=True)}
    assert utc_first[dt.date(2024, 3, 8)] == 14 and utc_first[dt.date(2024, 3, 11)] == 13
    assert validate_bars(df, meta) == []


def test_F_0_1_2_hourly_half_day_has_four_bars(tmp_path: Path, adapter: AlpacaAdapter) -> None:
    files = raw_file(tmp_path, "1H", "AAPL", 2024, "hourly_2024.json")
    df, _ = adapter.to_canonical(files, timeframe="1H", symbol="AAPL")
    ny = df["ts"].dt.convert_time_zone(NY)
    half = ny.filter(ny.dt.date() == dt.date(2024, 11, 29))
    assert half.dt.hour().to_list() == [9, 10, 11, 12]


def test_F_0_1_2_metadata_fields(tmp_path: Path, adapter: AlpacaAdapter) -> None:
    files = raw_file(tmp_path, "1H", "AAPL", 2024, "hourly_2024.json")
    df, meta = adapter.to_canonical(files, timeframe="1H", symbol="AAPL")
    assert (meta.source, meta.feed, meta.adjustment, meta.volume_quality) == (
        "alpaca",
        "sip",
        "split",
        "full",
    )
    assert (meta.price_type, meta.bar_label, meta.session) == ("trade", "start", "RTH_hour_aligned")
    assert (meta.symbol, meta.source_symbol, meta.asset_class, meta.timeframe) == (
        "AAPL",
        "AAPL",
        "us_equity",
        "1H",
    )
    assert "pre-market" in meta.notes
    assert len(meta.raw_refs) == 1 and meta.raw_refs[0].path.endswith("2024.parquet")
    assert meta.downloaded_at is not None
    assert {"vwap", "trades"} <= set(df.columns)
    _, dmeta = adapter.to_canonical(
        raw_file(tmp_path, "1D", "AAPL", 2020, "daily_2020.json"), timeframe="1D", symbol="AAPL"
    )
    assert dmeta.session == "exchange"


def test_F_0_1_2_identical_duplicate_chunks_are_deduplicated(
    tmp_path: Path, adapter: AlpacaAdapter
) -> None:
    rows = load_fixture("daily_2020.json")["AAPL"]
    write_chunk(tmp_path, "1D", "AAPL", 2020, rows, REQ, False, "fake 0")
    write_chunk(tmp_path, "1D", "AAPL", 2020, rows[:5], REQ, True, "fake 0")  # overlapping v2
    d = tmp_path / "us_equity" / "alpaca_sip_split" / "1D" / "AAPL"
    files = sorted(d.glob("*.parquet"))
    assert [f.name for f in files] == ["2020.parquet", "2020.v2.parquet"]
    df, _ = adapter.to_canonical(files, timeframe="1D", symbol="AAPL")
    assert df.height == len(rows)


def test_F_0_1_2_conflicting_duplicate_chunks_are_critical(
    tmp_path: Path, adapter: AlpacaAdapter
) -> None:
    rows = load_fixture("daily_2020.json")["AAPL"]
    changed = [dict(rows[0], c=rows[0]["c"] + 1.0), *rows[1:3]]
    write_chunk(tmp_path, "1D", "AAPL", 2020, rows, REQ, False, "fake 0")
    write_chunk(tmp_path, "1D", "AAPL", 2020, changed, REQ, True, "fake 0")
    files = sorted((tmp_path / "us_equity" / "alpaca_sip_split" / "1D" / "AAPL").glob("*.parquet"))
    with pytest.raises(DataError, match="conflicting values") as exc:
        adapter.to_canonical(files, timeframe="1D", symbol="AAPL")
    assert exc.value.symbol == "AAPL"


def test_F_0_1_2_latest_version_is_used_for_ingest(tmp_path: Path) -> None:
    rows = load_fixture("daily_2020.json")["AAPL"]
    write_chunk(tmp_path, "1D", "AAPL", 2020, rows[:3], REQ, False, "fake 0")
    write_chunk(tmp_path, "1D", "AAPL", 2020, rows, REQ, True, "fake 0")
    assert [p.name for p in latest_chunks(tmp_path, "1D", "AAPL")] == ["2020.v2.parquet"]


def test_F_0_1_2_ingest_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw"
    store_root = tmp_path / "store"
    for sym in ("AAPL", "TSLA"):
        write_chunk(raw, "1D", sym, 2020, load_fixture("daily_2020.json")[sym], REQ, True, "fake 0")
    store, catalog, cfg = SnapshotStore(store_root), Catalog(store_root), make_config()
    res = ingest_alpaca_symbol("AAPL", "1D", raw, store, catalog, cfg)
    assert res.status == "ingested" and res.is_reference and res.rows == 11
    ref = catalog.get_reference("AAPL", "1D")
    assert ref.snapshot_hash == res.snapshot_hash
    assert "No cross-check file" in ref.notes
    report = pl.read_csv(raw / "_reports" / "alpaca_split_check_1D.csv")
    aapl = report.filter(pl.col("date") == "2020-08-31")
    assert aapl["verdict"].to_list() == ["adjusted"]
    # a second ingest of the same raw data is idempotent and keeps the reference
    again = ingest_alpaca_symbol("AAPL", "1D", raw, store, catalog, cfg)
    assert again.snapshot_hash == res.snapshot_hash
    assert catalog.list_snapshots(symbol="AAPL").height == 1

    # CLI: sfac data list shows the snapshot
    monkeypatch.setenv("SFAC_DATA_ROOT", str(store_root))
    monkeypatch.chdir(tmp_path)
    out = CliRunner().invoke(app, ["data", "list"])
    assert (
        out.exit_code == 0 and "AAPL" in out.output and (res.snapshot_hash or "")[:12] in out.output
    )


def test_F_0_1_2_ingest_skips_symbol_without_data(tmp_path: Path) -> None:
    write_chunk(tmp_path, "1D", "DLSTD", 2020, [], REQ, True, "fake 0")
    res = ingest_alpaca_symbol(
        "DLSTD",
        "1D",
        tmp_path,
        SnapshotStore(tmp_path / "s"),
        Catalog(tmp_path / "s"),
        make_config(),
    )
    assert res.status == "no_data"


def test_F_0_1_2_ingest_records_historical_pit_ticker(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    rows = load_fixture("daily_2020.json")["AAPL"]
    write_chunk(raw, "1D", "META", 2020, rows, REQ, True, "fake 0")
    store, catalog = SnapshotStore(tmp_path / "s"), Catalog(tmp_path / "s")
    res = ingest_alpaca_symbol("META", "1D", raw, store, catalog, make_config(), pit_symbol="FB")
    meta = catalog.get_reference("META", "1D")
    assert res.status == "ingested" and meta.source_symbol == "META"
    assert "Historical (S&P 500 PIT) ticker: FB; downloaded as META." in meta.notes


# --- T04g / D-397: an unadjusted known split fails that symbol, not the run -------------------


def _unadjusted_aapl(raw: Path) -> None:
    """AAPL 2020 with the 4:1 split of 2020-08-31 NOT applied to the pre-split bars."""
    rows = [dict(r) for r in load_fixture("daily_2020.json")["AAPL"]]
    for r in rows:
        if r["t"][:10] < "2020-08-31":
            for k in ("o", "h", "l", "c"):
                r[k] = r[k] * 4.0
    write_chunk(raw, "1D", "AAPL", 2020, rows, REQ, True, "fake 0")


def test_F_0_1_2_D_397_an_unadjusted_known_split_fails_that_symbol(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _unadjusted_aapl(raw)
    store, catalog = SnapshotStore(tmp_path / "s"), Catalog(tmp_path / "s")
    res = ingest_alpaca_symbol("AAPL", "1D", raw, store, catalog, make_config())
    assert res.status == "unadjusted_split"
    assert "2020-08-31" in res.split_warning
    assert catalog.list_snapshots(symbol="AAPL").height == 0  # nothing ingested
    report = pl.read_csv(raw / "_reports" / "alpaca_split_check_1D.csv")
    assert "unadjusted" in report["verdict"].to_list()  # it is listed, as D-397 asks


def test_F_0_1_2_D_397_one_unadjusted_symbol_does_not_stop_the_others(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _unadjusted_aapl(raw)
    write_chunk(raw, "1D", "TSLA", 2020, load_fixture("daily_2020.json")["TSLA"], REQ, True, "f")
    store, catalog, cfg = SnapshotStore(tmp_path / "s"), Catalog(tmp_path / "s"), make_config()
    out = [ingest_alpaca_symbol(s, "1D", raw, store, catalog, cfg) for s in ("AAPL", "TSLA")]
    assert [r.status for r in out] == ["unadjusted_split", "ingested"]


def test_F_0_1_2_T04g_the_ingest_reads_the_universe_and_the_exclusion_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task section 1: symbols = the universe CSV minus the exclusion CSV, never hard-coded."""
    raw = tmp_path / "raw"
    for sym in ("AAPL", "TSLA"):
        write_chunk(raw, "1D", sym, 2020, load_fixture("daily_2020.json")[sym], REQ, True, "f")
    universe = tmp_path / "u.csv"
    universe.write_text("symbol\nAAPL\nTSLA\n", encoding="utf-8")
    excluded = tmp_path / "x.csv"
    excluded.write_text("symbol,reason,evidence\nTSLA,re-used,see T04i\n", encoding="utf-8")
    monkeypatch.setenv("SFAC_RAW_ROOT", str(raw))
    monkeypatch.setenv("SFAC_DATA_ROOT", str(tmp_path / "s"))
    out = CliRunner().invoke(
        app,
        [
            "data",
            "ingest",
            "alpaca",
            "--timeframe",
            "1D",
            "--universe",
            str(universe),
            "--excluded",
            str(excluded),
        ],
    )
    assert out.exit_code == 0, out.output
    assert "AAPL" in out.output and "1 excluded" in out.output
    assert Catalog(tmp_path / "s").list_snapshots(symbol="TSLA").height == 0
