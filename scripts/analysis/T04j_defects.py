"""T04j plan: do the T04k/T04l defect families occur in the Dukascopy h1 feed? Measured, not assumed.

Local only; reads the raw h1 months (read-only, D-028), builds the canonical mid series **in
memory** with the existing adapter (months present on both sides only), and writes a CSV. Nothing is
stored::

    uv run python scripts/analysis/T04j_defects.py                     # every D-661 window
    uv run python scripts/analysis/T04j_defects.py --symbols EURUSD,XAUUSD

The plan measured six near-complete instruments (``docs/reviews/T04j_defects.csv``, kept as the
plan's record). Before an ingest, D-717 re-measures on the **complete** raw set: by default the
instruments with a D-661 window now, measured over that window. Rows are upserted by symbol into
``docs/reviews/T04j_defects_ingest.csv``, and the exit code is **1 when any defect family is present**
(frozen stretches, long gaps, bad prints): T04j then stops and raises; nothing is absorbed.

Per instrument, the families measured on the Alpaca sets:

* **frozen stretches** (D-398 (1): identical close and zero range for >= ``frozen_min_sessions``
  bars) -- padding;
* **long gaps** (D-708: >= ``relisting.gap_days`` between bars) -- a re-use would show here;
* **bad prints** (the D-703/D-706 wick rule on the hourly mid) and **spread spikes** (spread above
  ``k`` x its rolling median);
* **weekend bars** (Saturday/Sunday UTC) -- what D-010's Sunday merge will fold into Monday;
* **weekday holes**: missing hours inside a trading week (a weekday hour with no bar while the
  hours around it trade);
* and, on the in-memory D-032 daily series (``resample_bars``, research mode), the **D-008** split.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import polars as pl

from strategy_factory.cli import utf8_output
from strategy_factory.data.adapters.dukascopy import DukascopyAdapter
from strategy_factory.data.clean_daily import wick_outliers
from strategy_factory.data.config import (
    AlpacaConfig,
    QualityConfig,
    ResampleConfig,
    SplitConfig,
    load_alpaca_config,
    load_dukascopy_config,
    load_quality_config,
    load_split_config,
)
from strategy_factory.data.coverage import dukascopy_coverage_frame, dukascopy_windows
from strategy_factory.data.download.dukascopy import load_instruments
from strategy_factory.data.download.rawfiles import is_settled, raw_root, version_of
from strategy_factory.data.relisting import frozen_stretches
from strategy_factory.data.resample import resample_bars
from strategy_factory.data.split import HistoryTooShortError, compute_split

OUT = Path("docs") / "reviews" / "T04j_defects_ingest.csv"
UNIVERSE = Path("configs") / "universe" / "dukascopy.csv"
#: measurement only (not a data rule): a spread above this many times its 500-bar rolling median
SPREAD_SPIKE_X = 10.0
#: the T04k / T04l families whose presence stops T04j before an ingest (D-717)
FAMILIES = ("frozen_stretches", "long_gaps", "wick_flags")


def _latest(folder: Path) -> dict[str, Path]:
    best: dict[str, tuple[int, Path]] = {}
    for f in folder.glob("*.csv.gz"):
        if not is_settled(f):  # the download runs alongside: skip a month still being written
            continue
        base, n = version_of(f, ".csv.gz")
        if base not in best or n > best[base][0]:
            best[base] = (n, f)
    return {k: v[1] for k, v in best.items()}


def measure(
    inst: str,
    sym: str,
    cls: str,
    root: Path,
    adapter: DukascopyAdapter,
    alpaca: AlpacaConfig,
    quality: QualityConfig,
    split_cfg: SplitConfig,
    window: tuple[str, str] | None = None,
) -> dict[str, object]:
    """One instrument's row: every family, on the months present on both sides -- only those of
    ``window`` (first, last month; D-661) when given."""
    bid, ask = _latest(root / sym / "bid"), _latest(root / sym / "ask")
    months = sorted(set(bid) & set(ask))
    if window is not None:
        months = [m for m in months if window[0] <= m <= window[1]]
    paths = [bid[m] for m in months] + [ask[m] for m in months]
    bars, meta = adapter.to_canonical(paths, symbol=sym, instrument=inst, asset_class=cls)
    bars = bars.sort("ts")
    wd = bars["ts"].dt.weekday()
    frozen = frozen_stretches(
        bars["high"].to_list(),
        bars["low"].to_list(),
        bars["close"].to_list(),
        alpaca.relisting.frozen_min_sessions,
    )
    gaps = bars.with_columns(pl.col("ts").diff().dt.total_days().alias("g")).filter(
        pl.col("g") >= alpaca.relisting.gap_days
    )
    w = wick_outliers(bars.select("ts", "open", "high", "low", "close"), quality.daily_wick_outlier)
    med = bars["spread"].rolling_median(window_size=500, min_samples=50)
    spikes = int((bars["spread"] > SPREAD_SPIKE_X * med).sum())
    # weekday holes: an hour missing between two bars less than a day apart, Mon-Thu
    step = bars.with_columns(pl.col("ts").diff().alias("d"))
    holes = step.filter(
        (pl.col("d") > dt.timedelta(hours=1))
        & (pl.col("d") < dt.timedelta(hours=24))
        & pl.col("ts").dt.weekday().is_in([2, 3, 4, 5])
    )
    missing_hours = int((holes["d"].dt.total_hours() - 1).sum())
    daily = resample_bars(bars, meta, "1D", "research", ResampleConfig(), quality)
    key = meta.model_copy(update={"snapshot_hash": "0" * 64}).key()  # in memory: no hash
    split_h = split_d = True
    try:
        compute_split(bars["ts"], key, split_cfg)
    except HistoryTooShortError:
        split_h = False
    try:
        compute_split(daily.bars["ts"], key, split_cfg)
    except HistoryTooShortError:
        split_d = False
    return {
        "symbol": sym,
        "asset_class": cls,
        "window_first": months[0] if months else None,
        "window_last": months[-1] if months else None,
        "months_both_sides": len(months),
        "bars_1h": bars.height,
        "first": str(bars["ts"].min())[:10],
        "last": str(bars["ts"].max())[:10],
        "frozen_stretches": len(frozen),
        "frozen_bars": sum(e - s + 1 for s, e in frozen),
        "long_gaps": gaps.height,
        "longest_gap_days": int(bars["ts"].diff().dt.total_days().max() or 0),
        "wick_flags": w.filter(pl.col("flag_high") | pl.col("flag_low")).height,
        "spread_spikes": spikes,
        "zero_or_neg_spread": int((bars["spread"] <= 0).sum()),
        "saturday_bars": int((wd == 6).sum()),
        "sunday_bars": int((wd == 7).sum()),
        "weekday_missing_hours": missing_hours,
        "bars_1d": daily.bars.height,
        "thin_days_flagged": daily.flags.height,
        "weekend_daily_bars": int(daily.bars["ts"].dt.weekday().is_in([6, 7]).sum()),
        "d008_1h": split_h,
        "d008_1d": split_d,
    }


def present(row: dict[str, object]) -> list[str]:
    """The D-717 families present in a measured row (empty: the instrument may be ingested)."""
    return [f for f in FAMILIES if int(str(row[f])) > 0]


def current_windows() -> dict[str, tuple[str, str]]:
    """Every instrument's D-661 window now (first, last month); none for an instrument without."""
    cfg = load_dukascopy_config()
    insts = load_instruments(cfg.universe_file)
    today = dt.datetime.now(dt.UTC).date()
    frame = dukascopy_coverage_frame(raw_root(), "h1", insts, cfg.h1_start, today)
    return {s: (w.first, w.last) for s, w in dukascopy_windows(frame).items() if w.first}


def run(
    symbols: list[str], windows: dict[str, tuple[str, str]] | None = None, out: Path = OUT
) -> pl.DataFrame:
    """Measure ``symbols`` (over their windows when given), upsert their rows (by symbol) into
    ``out``; return the new rows."""
    root = raw_root() / "fx_metals_cfd" / "dukascopy" / "h1"
    universe = pl.read_csv(UNIVERSE)
    alpaca, quality, split_cfg = load_alpaca_config(), load_quality_config(), load_split_config()
    adapter = DukascopyAdapter(load_dukascopy_config())
    measured_on = dt.datetime.now(dt.UTC).date().isoformat()
    rows = [
        {
            **measure(
                inst,
                sym,
                cls,
                root,
                adapter,
                alpaca,
                quality,
                split_cfg,
                (windows or {}).get(sym),
            ),
            "measured_on": measured_on,
        }
        for inst, sym, cls in universe.select("instrument_id", "symbol", "asset_class").rows()
        if sym in symbols
    ]
    new = pl.DataFrame(rows)
    if out.is_file() and new.height:
        old = pl.read_csv(out).filter(~pl.col("symbol").is_in(new["symbol"].to_list()))
        merged = pl.concat([old, new], how="diagonal_relaxed") if old.height else new
    else:
        merged = new
    if merged.height:
        merged.sort("symbol").write_csv(out)
    return new


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", help="Comma-separated symbols (default: every window).")
    args = parser.parse_args(argv)
    utf8_output()
    windows = current_windows()
    symbols = (
        [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else list(windows)
    )
    if not symbols:
        print("no instrument to measure: none has a complete window (D-661)")
        return 0
    new = run(symbols, windows)
    pl.Config.set_tbl_rows(40)
    pl.Config.set_tbl_cols(25)
    pl.Config.set_tbl_width_chars(260)
    print(new)
    found = {r["symbol"]: present(r) for r in new.iter_rows(named=True) if present(r)}
    if found:
        print(f"STOP (D-717): defect families present, nothing may be ingested: {found}")
        return 1
    print(f"D-717: no defect family in {len(symbols)} instrument(s): {', '.join(symbols)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
