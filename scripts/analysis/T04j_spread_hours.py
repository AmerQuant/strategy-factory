"""T04j / P-87: the Dukascopy spread by UTC hour -- what a daily cost must not be built from.

Local only; reads the raw h1 months (read-only), builds the mid series in memory (months present on
both sides), writes ``docs/reviews/T04j_spread_by_hour.csv``; nothing is stored::

    uv run python scripts/analysis/T04j_spread_hours.py

Per instrument: the cost table itself (``costs.arrays.hourly_spread_table``, D-716) divided by the
instrument's median spread over all bars (1.0 = typical) -- 24 UTC hours with the week opens taken
out, and the ``week_open`` key (the first bar of each trading week, the Sunday open, which under
D-010 is also the open of Monday's daily bar). Scaling to the broker (D-523) multiplies every row by
the same factor, so these ratios are the ones the resolved profile carries.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from strategy_factory.costs.arrays import hourly_spread_table
from strategy_factory.data.adapters.dukascopy import DukascopyAdapter
from strategy_factory.data.config import load_dukascopy_config
from strategy_factory.data.download.rawfiles import raw_root, version_of

OUT = Path("docs") / "reviews" / "T04j_spread_by_hour.csv"
UNIVERSE = Path("configs") / "universe" / "dukascopy.csv"
SYMBOLS = ("EURUSD", "GBPUSD", "GBPCHF", "CADJPY", "XAUUSD", "XAGUSD")


def _latest(folder: Path) -> dict[str, Path]:
    best: dict[str, tuple[int, Path]] = {}
    for f in folder.glob("*.csv.gz"):
        base, n = version_of(f, ".csv.gz")
        if base not in best or n > best[base][0]:
            best[base] = (n, f)
    return {k: v[1] for k, v in best.items()}


def main() -> None:
    root = raw_root() / "fx_metals_cfd" / "dukascopy" / "h1"
    universe = pl.read_csv(UNIVERSE).filter(pl.col("symbol").is_in(list(SYMBOLS)))
    adapter = DukascopyAdapter(load_dukascopy_config())
    frames = []
    for inst, sym, cls in universe.select("instrument_id", "symbol", "asset_class").rows():
        bid, ask = _latest(root / sym / "bid"), _latest(root / sym / "ask")
        months = sorted(set(bid) & set(ask))
        bars, _ = adapter.to_canonical(
            [bid[m] for m in months] + [ask[m] for m in months],
            symbol=sym,
            instrument=inst,
            asset_class=cls,
        )
        bars = bars.sort("ts")
        overall = float(bars["spread"].median())  # type: ignore[arg-type]
        ts_us = bars["ts"].dt.epoch("us").to_numpy().astype(np.int64)
        table = hourly_spread_table(ts_us, bars["spread"].to_numpy(), 1.0, float("nan"))
        rel = [float(v) / overall for v in table.full_spread]
        rel.append((table.week_open or float("nan")) / overall)
        keys = [f"{h:02d}" for h in range(24)] + ["week_open"]
        counts = [int(c) for c in table.counts] + [table.week_open_count]
        frames.append(
            pl.DataFrame(
                {"key": keys, "symbol": sym, "rel": [round(v, 3) for v in rel], "bars": counts}
            )
        )
    long = pl.concat(frames)
    out = long.pivot(on="symbol", index="key", values="rel", maintain_order=True)
    print(long.filter(pl.col("key") == "week_open"))
    out.write_csv(OUT)
    pl.Config.set_tbl_rows(30)
    pl.Config.set_float_precision(2)
    print(out)


if __name__ == "__main__":
    main()
