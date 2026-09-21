"""F-0.1.8 / F-0.1.6 (T04k): the clean pass end to end -- `sfac data clean` per symbol.

Covers what the unit tests of the arms cannot: the order in which a boundary is decided (leading
pad, D-397, D-700 names), that the input is always the raw snapshot (V3), that every clean
snapshot has its own log and provenance keyed by its hash (S6), that the metadata carries the
config hash and the boundary (V4), and that the quality report is written in the same pass (V2).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl
import pytest
from fixtures.alpaca_helpers import make_config
from fixtures.bars import make_meta

from strategy_factory.data import cli_clean
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.cli_clean import (
    CLEAN_DECISIONS,
    CLEAN_DIR,
    CleanContext,
    NameSources,
    _clean_symbol,
    _settle,
    input_rows,
)
from strategy_factory.data.config import QualityConfig
from strategy_factory.data.crosscheck import UNSETTLED
from strategy_factory.data.name_evidence import NameChange, changes_by_symbol
from strategy_factory.data.quality import QUALITY_DIR
from strategy_factory.data.relisting import analyse_series
from strategy_factory.data.store import SnapshotStore

START = dt.datetime(2020, 1, 2, tzinfo=dt.UTC)
Bar = tuple[float, float, float, float]


def _daily(rows: list[Bar]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": [START + dt.timedelta(days=i) for i in range(len(rows))],
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "volume": [1000.0] * len(rows),
        }
    )


def _real(n: int, price: float) -> list[Bar]:
    return [(price, price + 0.5, price - 0.5, price) for _ in range(n)]


def _pad(n: int, price: float) -> list[Bar]:
    return [(price, price, price, price)] * n


def _ctx(tmp_path: Path, names: NameSources | None = None) -> CleanContext:
    store_root, raw = tmp_path / "store", tmp_path / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    store = SnapshotStore(store_root)
    return CleanContext(
        store=store,
        catalog=Catalog(store_root),
        alpaca=make_config(),
        quality=QualityConfig(),
        root=raw,
        expected=pl.DataFrame(schema={"session_date": pl.Date(), "expected_bars": pl.UInt32()}),
        splits={},
        names=names or NameSources({}, {}, 7),
        out_dir=store_root / CLEAN_DIR,
        fingerprint="f" * 64,
    )


def _register(ctx: CleanContext, symbol: str, rows: list[Bar]) -> dict[str, object]:
    meta = make_meta(source="alpaca", source_symbol=symbol, symbol=symbol, session="exchange")
    stored = ctx.catalog.register(ctx.store.write_snapshot(_daily(rows), meta))
    ctx.catalog.set_reference(symbol, "1D", stored.snapshot_hash or "", note="raw")
    return input_rows(ctx.catalog).filter(pl.col("symbol") == symbol).row(0, named=True)


def _run(ctx: CleanContext, row: dict[str, object], set_reference: bool = False) -> dict:
    short: list[dict[str, object]] = []
    return _clean_symbol(row, ctx, set_reference, short)


# ------------------------------------------------------------------ the boundary decision order


def test_F_0_1_8_T04k_a_leading_pad_is_trimmed_without_any_name_evidence(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    row = _register(ctx, "IPO", _pad(40, 5.0) + _real(60, 30.0))
    out = _run(ctx, row)
    assert out["boundary_reason"] == "leading_padding"
    assert out["boundary_applied"] is True
    assert out["clean_bars"] == 60 and out["status"] == "cleaned"


def test_F_0_1_8_T04k_one_name_keeps_the_history_and_cuts_only_the_pad(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    row = _register(ctx, "ONE", _real(60, 100.0) + _pad(30, 100.0) + _real(60, 20.0))
    out = _run(ctx, row)
    assert out["boundary_reason"] == "stale_run"
    assert out["name_verdict"] == "one_name"
    assert out["boundary_applied"] is False
    assert out["clean_bars"] == 120  # both real stretches kept, only the pad removed
    assert out["boundary_trim"] == 0 and out["frozen_cut"] == 30


def test_F_0_1_8_T04k_a_re_use_by_name_trims_at_the_boundary(tmp_path: Path) -> None:
    rows = _real(60, 100.0) + _pad(30, 100.0) + _real(60, 20.0)
    break_start = (START + dt.timedelta(days=60)).date()  # the first padded bar
    names = NameSources(
        {"OLD": "Old Company Inc.", "NEWCO": "Old Company Inc. (moved)"},
        changes_by_symbol([NameChange("OLD", "NEWCO", break_start)]),
        7,
    )
    ctx = _ctx(tmp_path, names)
    out = _run(ctx, _register(ctx, "OLD", rows))
    assert out["name_verdict"] == "re_use"
    assert out["boundary_applied"] is True
    assert out["clean_bars"] == 60  # only the new holder's bars


def test_F_0_1_8_T04k_an_unadjusted_split_takes_the_d397_path(tmp_path: Path) -> None:
    """The cross-check is continuous between two real bars where the ingested series drops 10x."""
    rows = _real(60, 100.0) + _pad(30, 100.0) + _real(60, 10.0)
    ctx = _ctx(tmp_path)
    xdir = ctx.root / "us_equity" / "alpaca_sip_all" / "1D"
    xdir.mkdir(parents=True)
    days = [(START + dt.timedelta(days=i)).date() for i in range(len(rows))]
    closes = [100.0] * 59 + [100.0] * 31 + [100.5] * 60  # continuous: no 10x break
    pl.DataFrame(
        {
            "date": [d.isoformat() for d in days],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1.0] * len(days),
        }
    ).write_csv(xdir / "us_SPLIT.csv")
    out = _run(ctx, _register(ctx, "SPLIT", rows))
    assert out["status"] == "unadjusted_split"
    assert "--refresh" in out["note"] and "2016-01-01" in out["note"]
    assert ctx.catalog.table().filter(pl.col("derived_from").is_not_null()).height == 0


# ------------------------------------------------------------------------- V3, S6, V4, V2


def test_F_0_1_8_T04k_the_input_is_the_raw_snapshot_even_after_set_reference(
    tmp_path: Path,
) -> None:
    """V3: once the clean snapshot is the reference, a re-run must still start from raw."""
    ctx = _ctx(tmp_path)
    rows = _real(40, 100.0)
    rows[30] = (100.0, 160.0, 99.5, 101.0)  # a wick the clip arm takes (no hourly series)
    row = _register(ctx, "WICK", rows)
    first = _run(ctx, row, set_reference=True)
    assert first["status"] == "cleaned" and first["wick_clip"] == 1
    catalog_before = ctx.catalog.table().sort("snapshot_hash")
    again = input_rows(ctx.catalog)
    assert again.height == 1 and again["derived_from"].is_null().all()  # still the raw one
    second = _run(ctx, again.row(0, named=True), set_reference=True)
    assert second["snapshot_hash"] == first["snapshot_hash"]  # no clean-of-clean
    assert second["wick_clip"] == 1
    assert ctx.catalog.table().sort("snapshot_hash").equals(catalog_before)


def test_F_0_1_8_T04k_each_clean_snapshot_has_its_own_log_and_provenance(tmp_path: Path) -> None:
    """S6/V4: keyed by the clean hash, with the config hash and the boundary."""
    ctx = _ctx(tmp_path)
    out = _run(ctx, _register(ctx, "IPO", _pad(40, 5.0) + _real(60, 30.0)))
    folder = ctx.out_dir / "IPO"
    log = pl.read_csv(folder / f"{out['snapshot_hash']}.csv")
    prov = json.loads((folder / f"{out['snapshot_hash']}.json").read_text(encoding="utf-8"))
    assert log.height == out["changed_bars"]
    assert prov["config_hash"] == "f" * 64
    assert prov["boundary"]["applied"] is True
    assert prov["boundary"]["reason"] == "leading_padding"
    meta = ctx.catalog.get_reference("IPO", "1D")  # still raw: no --set-reference here
    derived = ctx.catalog.table().filter(pl.col("derived_from").is_not_null()).row(0, named=True)
    assert "config ffffffffffffffff" in derived["notes"]
    assert "History starts" in derived["notes"]
    assert meta.derived_from is None


def test_F_0_1_8_T04k_the_quality_report_is_written_in_the_same_pass(tmp_path: Path) -> None:
    """V2: the report the research reads carries both T04k checks."""
    ctx = _ctx(tmp_path)
    out = _run(ctx, _register(ctx, "IPO", _pad(40, 5.0) + _real(60, 30.0)))
    report = ctx.store.root / QUALITY_DIR / f"{out['snapshot_hash']}.json"
    codes = {c["code"] for c in json.loads(report.read_text(encoding="utf-8"))["checks"]}
    assert {"daily_wick_outlier", "daily_extreme_unsupported"} <= codes
    assert out["quality_status"] in {"ok", "warning", "critical"}


# ------------------------------------------------------------------------------------ TBRG


def test_F_0_1_8_T04k_the_crosscheck_compares_the_last_real_bar_never_the_pad(
    tmp_path: Path,
) -> None:
    """`TBRG`: the ingested pad sat at a stale 13.31 while MS-US-1D traded near 9.

    Comparing the pad with the boundary made the ingested series "jump" and the cross-check look
    continuous. From the last *real* bar both feeds make the same move: unsettled, never a split.
    """
    rows = _real(60, 13.31) + _pad(30, 13.31) + _real(40, 7.67)
    days = [(START + dt.timedelta(days=i)).date() for i in range(len(rows))]
    cross = [13.31] * 60 + [9.2] * 30 + [7.67] * 40  # the cross-check traded during the pad
    ctx = _ctx(tmp_path)
    xdir = ctx.root / "us_equity" / "alpaca_sip_all" / "1D"
    xdir.mkdir(parents=True)
    pl.DataFrame(
        {
            "date": [d.isoformat() for d in days],
            "open": cross,
            "high": cross,
            "low": cross,
            "close": cross,
            "volume": [1.0] * len(days),
        }
    ).write_csv(xdir / "us_TBRG.csv")
    daily = _daily(rows)
    verdict = analyse_series(
        "TBRG",
        days,
        daily["high"].to_list(),
        daily["low"].to_list(),
        daily["close"].to_list(),
        0.40,
    )
    got = _settle("TBRG", verdict, daily, ctx.root, ctx.alpaca)
    assert got.verdict == UNSETTLED
    assert "both feeds break alike" in got.evidence


# ------------------------------------------------ round 3: judge the clean series on its own bars


def test_F_0_1_8_T04k_a_capped_extreme_is_not_reported_again_on_the_clean_series() -> None:
    """The first full pass fed the clean snapshot's check the breaches of the RAW bars, so 620
    hourly symbols were flagged for extremes `extreme_cap` had already corrected."""
    from strategy_factory.data.clean_daily import clean_daily
    from strategy_factory.data.cli_clean import HourlyEvidence

    rows = _real(30, 100.0)
    rows[20] = (100.0, 130.0, 99.5, 100.0)  # the daily high the hourly feed never reached
    daily = _daily(rows)
    days = [(START + dt.timedelta(days=i)).date() for i in range(30)]
    rth = pl.DataFrame(
        {
            "session_date": days,
            "rth_high": [100.5] * 30,
            "rth_low": [99.5] * 30,
            "rth_bars": [7] * 30,
        },
        schema={
            "session_date": pl.Date(),
            "rth_high": pl.Float64(),
            "rth_low": pl.Float64(),
            "rth_bars": pl.UInt32(),
        },
    )
    raw = rth.rename({"rth_high": "raw_high", "rth_low": "raw_low", "rth_bars": "raw_bars"})
    expected = pl.DataFrame(
        {"session_date": days, "expected_bars": [7] * 30},
        schema={"session_date": pl.Date(), "expected_bars": pl.UInt32()},
    )
    ev = HourlyEvidence(
        "EQ",
        rth,
        raw,
        rth.select("session_date", "rth_bars").join(expected, on="session_date"),
        expected,
        QualityConfig().daily_extreme_unsupported.eps_bps,
    )
    assert ev.breaches(daily).height == 1  # the raw series breaches once
    clean, log = clean_daily(
        daily, "EQ", QualityConfig(), breaches=ev.breaches(daily), has_hourly=True
    )
    assert log.height == 1 and log["arm"][0] == "extreme_cap"
    assert ev.breaches(clean).height == 0  # judged on its own bars, the clean series is clean


def test_F_0_1_8_T04k_the_pass_judges_the_clean_series_with_real_hourly_files(
    tmp_path: Path,
) -> None:
    """S-a: the whole path with hourly raw files on disk -- `_hourly_evidence`, the cap, and the
    quality report of the clean snapshot judged on the CLEAN bars (§7.4).

    If the pass handed the report the raw bars' breaches, the capped day would still be counted.
    """
    from fixtures.alpaca_helpers import load_fixture

    from strategy_factory.data.daily_session import expected_bars
    from strategy_factory.data.download.alpaca import write_chunk
    from strategy_factory.data.download.alpaca_reference import load_sessions

    ctx = _ctx(tmp_path)
    write_chunk(
        ctx.root,
        "1H",
        "AAPL",
        2024,
        load_fixture("hourly_2024.json")["AAPL"],
        {"feed": "sip", "adjustment": "split"},
        True,
        "fake 0",
    )
    cfg = ctx.alpaca
    ctx = CleanContext(
        **{
            **ctx.__dict__,
            "expected": expected_bars(
                load_sessions(cfg.hourly_session.sessions_file), cfg.hourly_session.first_bar
            ),
        }
    )
    days = [dt.datetime(2024, 3, 8, tzinfo=dt.UTC), dt.datetime(2024, 3, 11, tzinfo=dt.UTC)]
    days.append(dt.datetime(2024, 11, 29, tzinfo=dt.UTC))
    daily = pl.DataFrame(
        {
            "ts": days,
            "open": [171.0, 173.0, 238.0],
            "high": [200.0, 173.7, 238.4],  # 2024-03-08: a high no hourly bar reached (RTH 171.7)
            "low": [170.6, 172.6, 237.6],
            "close": [171.2, 173.2, 238.1],
            "volume": [1000.0] * 3,
        }
    )
    meta = make_meta(source="alpaca", source_symbol="AAPL", symbol="AAPL", session="exchange")
    stored = ctx.catalog.register(ctx.store.write_snapshot(daily, meta))
    ctx.catalog.set_reference("AAPL", "1D", stored.snapshot_hash or "", note="raw")
    row = input_rows(ctx.catalog).row(0, named=True)

    out = _run(ctx, row)
    assert out["has_hourly"] is True
    assert out["extreme_cap"] == 1 and out["wick_clip"] == 0
    report = ctx.store.root / QUALITY_DIR / f"{out['snapshot_hash']}.json"
    check = next(
        c
        for c in json.loads(report.read_text(encoding="utf-8"))["checks"]
        if c["code"] == "daily_extreme_unsupported"
    )
    assert check["status"] == "pass"  # the capped day is not counted again
    assert check["details"]["short_hourly_days"] == 0


def test_F_0_1_8_T04k_one_raw_snapshot_per_symbol_after_a_refresh(tmp_path: Path) -> None:
    """S-c: a D-397 refresh and re-ingest leaves two raw snapshots; the newest is the input."""
    ctx = _ctx(tmp_path)
    old = _register(ctx, "RFR", _real(40, 100.0))
    meta = make_meta(source="alpaca", source_symbol="RFR", symbol="RFR", session="exchange")
    ctx.catalog.register(ctx.store.write_snapshot(_daily(_real(40, 101.0)), meta))
    rows = input_rows(ctx.catalog)
    assert rows.height == 1
    assert rows["snapshot_hash"][0] != old["snapshot_hash"]


# ------------------------------------------------------- the decisions named in the provenance


def test_F_0_1_8_T04k_notes_and_provenance_name_every_decision_of_the_pass(
    tmp_path: Path,
) -> None:
    """A reader asking why a bar changed gets the decisions, not only a hash to resolve."""
    ctx = _ctx(tmp_path)
    out = _run(ctx, _register(ctx, "IPO", _pad(40, 5.0) + _real(60, 30.0)))
    prov_file = ctx.out_dir / "IPO" / f"{out['snapshot_hash']}.json"
    prov = json.loads(prov_file.read_text(encoding="utf-8"))
    assert prov["decisions"] == list(CLEAN_DECISIONS)
    assert {"D-701", "D-703", "D-706"} <= set(prov["decisions"])
    derived = ctx.catalog.table().filter(pl.col("derived_from").is_not_null()).row(0, named=True)
    assert f"T04k clean daily ({'/'.join(CLEAN_DECISIONS)}), config " in derived["notes"]


def test_F_0_1_8_T04k_a_longer_decision_label_alone_is_not_stale_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Identical content written under the old label keeps its notes (D-392); only a different
    record -- config hash, arms, raw snapshot, boundary -- is flagged ``metadata_stale``."""
    ctx = _ctx(tmp_path)
    row = _register(ctx, "IPO", _pad(40, 5.0) + _real(60, 30.0))
    monkeypatch.setattr(cli_clean, "CLEAN_DECISIONS", ("D-396", "D-398", "D-399", "D-700"))
    first = _run(ctx, row)
    monkeypatch.undo()
    again = _run(ctx, row)
    assert again["snapshot_hash"] == first["snapshot_hash"]
    assert again["metadata_stale"] is False
    other = CleanContext(**{**ctx.__dict__, "fingerprint": "e" * 64})
    assert _run(other, row)["metadata_stale"] is True
