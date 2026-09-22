"""T04j plan: do the T04k/T04l defect families occur in the Dukascopy h1 feed? Measured, not assumed.

Local only; reads the raw h1 months (read-only, D-028) of the instruments whose raw set is close
to complete, builds the canonical mid series **in memory** with the existing adapter (months present
on both sides only), and writes ``docs/reviews/T04j_defects.csv``. Nothing is stored::

    uv run python scripts/analysis/T04j_defects.py

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

import datetime as dt
from pathlib import Path

import polars as pl

from strategy_factory.data.adapters.dukascopy import DukascopyAdapter
from strategy_factory.data.clean_daily import wick_outliers
from strategy_factory.data.config import (
    ResampleConfig,
    load_alpaca_config,
    load_dukascopy_config,
    load_quality_config,
    load_split_config,
)
from strategy_factory.data.download.rawfiles import raw_root, version_of
from strategy_factory.data.relisting import frozen_stretches
from strategy_factory.data.resample import resample_bars
from strategy_factory.data.split import HistoryTooShortError, compute_split

OUT = Path("docs") / "reviews" / "T04j_defects.csv"
UNIVERSE = Path("configs") / "universe" / "dukascopy.csv"
#: measurement only (not a data rule): a spread above this many times its 500-bar rolling median
SPREAD_SPIKE_X = 10.0


def _latest(folder: Path) -> dict[str, Path]:
    best: dict[str, tuple[int, Path]] = {}
    for f in folder.glob("*.csv.gz"):
        base, n = version_of(f, ".csv.gz")
        if base not in best or n > best[base][0]:
            best[base] = (n, f)
    return {k: v[1] for k, v in best.items()}


def main() -> None:
    root = raw_root() / "fx_metals_cfd" / "dukascopy" / "h1"
    universe = pl.read_csv(UNIVERSE)
    coverage = pl.read_csv(Path("docs") / "reviews" / "T04j_raw_coverage.csv")
    measured = (
        coverage.filter(pl.col("last") == pl.col("last").max())
        .filter(pl.col("missing_months") <= 20)["symbol"]
        .to_list()
    )
    alpaca, quality, split_cfg = load_alpaca_config(), load_quality_config(), load_split_config()
    adapter = DukascopyAdapter(load_dukascopy_config())
    rows = []
    for inst, sym, cls in universe.select("instrument_id", "symbol", "asset_class").rows():
        if sym not in measured:
            continue
        bid, ask = _latest(root / sym / "bid"), _latest(root / sym / "ask")
        months = sorted(set(bid) & set(ask))
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
        w = wick_outliers(
            bars.select("ts", "open", "high", "low", "close"), quality.daily_wick_outlier
        )
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
        rows.append(
            {
                "symbol": sym,
                "asset_class": cls,
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
        )
    out = pl.DataFrame(rows)
    out.write_csv(OUT)
    pl.Config.set_tbl_rows(40)
    pl.Config.set_tbl_cols(25)
    pl.Config.set_tbl_width_chars(260)
    print(out)


if __name__ == "__main__":
    main()
