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
from fixtures.alpaca_helpers import make_config
from fixtures.bars import make_meta

from strategy_factory.data.catalog import Catalog
from strategy_factory.data.cli_clean import (
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
