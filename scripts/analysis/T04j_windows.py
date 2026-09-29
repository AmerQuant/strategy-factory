"""T04j, D-661: how much history does each instrument's complete window keep? Measured, not assumed.

Local only; reads the raw h1 months (read-only, D-028) that are **settled** (data file and manifest
written, no ``.partial``: safe while the download runs), and writes
``docs/reviews/T04j_windows.csv``. Nothing is stored::

    uv run python scripts/analysis/T04j_windows.py

Per instrument: the D-661 window (the longest contiguous complete run of months ending at the last
complete month), its length, the gap that bounds it and the gaps before it, and **D-008** tested on
the actual bars of the window -- the 1H series built in memory by the adapter and its D-032 daily
series (``resample_bars``, research mode) -- with ``compute_split``, the same function the split
manager uses.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import polars as pl

from strategy_factory.cli import utf8_output
from strategy_factory.core.errors import SfacError
from strategy_factory.data.adapters.dukascopy import DukascopyAdapter
from strategy_factory.data.config import (
    ResampleConfig,
    load_dukascopy_config,
    load_quality_config,
    load_split_config,
)
from strategy_factory.data.coverage import (
    dukascopy_coverage_frame,
    dukascopy_windows,
    is_settled,
)
from strategy_factory.data.download.dukascopy import SIDES, latest_months, load_instruments
from strategy_factory.data.download.rawfiles import raw_root
from strategy_factory.data.resample import resample_bars
from strategy_factory.data.split import HistoryTooShortError, compute_split

OUT = Path("docs") / "reviews" / "T04j_windows.csv"


def _d008(ts: pl.Series, key: object, cfg: object) -> bool:
    try:
        compute_split(ts, key, cfg)  # type: ignore[arg-type]
    except HistoryTooShortError:
        return False
    return True


def main() -> int:
    utf8_output()
    cfg = load_dukascopy_config()
    insts = load_instruments(cfg.universe_file)
    root = raw_root()
    now = dt.datetime.now(dt.UTC)
    frame = dukascopy_coverage_frame(root, "h1", insts, cfg.h1_start, now.date())
    windows = dukascopy_windows(frame)
    adapter, quality, split_cfg = DukascopyAdapter(cfg), load_quality_config(), load_split_config()
    rows = []
    for inst in insts:
        w = windows[inst.symbol]
        required = frame.filter(pl.col("symbol") == inst.symbol, pl.col("required")).height
        row: dict[str, object] = {
            "symbol": inst.symbol,
            "asset_class": inst.asset_class,
            "required_from": w.required_from,
            "window_first": w.first,
            "window_last": w.last if w.first else None,
            "months": w.months,
            "years": w.years,
            "share_of_required": round(w.months / required, 3) if required else 0.0,
            "bounding_gap": w.bounding_gap,
            "missing_before": w.missing_before,
            "complete": w.complete,
            "bars_1h": 0,
            "bars_1d": 0,
            "d008_1h": False,
            "d008_1d": False,
            "note": "",
        }
        if w.first is not None:
            paths = [
                p
                for side in SIDES
                for p in latest_months(root, "h1", inst.instrument_id, side)
                if w.first <= p.name[:7] <= w.last and is_settled(p)
            ]
            try:
                bars, meta = adapter.to_canonical(
                    paths, symbol=inst.symbol, instrument=inst.instrument_id,
                    asset_class=inst.asset_class,
                )  # fmt: skip
                bars = bars.sort("ts")
                daily = resample_bars(bars, meta, "1D", "research", ResampleConfig(), quality)
                key = meta.model_copy(update={"snapshot_hash": "0" * 64}).key()
                row |= {
                    "bars_1h": bars.height,
                    "bars_1d": daily.bars.height,
                    "d008_1h": _d008(bars["ts"], key, split_cfg),
                    "d008_1d": _d008(daily.bars["ts"], key, split_cfg),
                }
            except SfacError as exc:
                row["note"] = f"adapter refused: {exc}"[:200]
        rows.append(row)
    out = pl.DataFrame(rows).with_columns(
        pl.lit(now.isoformat(timespec="minutes")).alias("measured_at")
    )
    out.write_csv(OUT)
    pl.Config.set_tbl_rows(40)
    pl.Config.set_tbl_cols(20)
    pl.Config.set_tbl_width_chars(250)
    print(out.drop("measured_at", "note", "asset_class"))
    notes = out.filter(pl.col("note") != "")
    if notes.height:
        print(notes.select("symbol", "note"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
