"""T04j / P-87: the Dukascopy spread by UTC hour -- what a daily cost must not be built from.

Local only; reads the raw h1 months (read-only), builds the mid series in memory (months present on
both sides), writes ``docs/reviews/T04j_spread_by_hour.csv``; nothing is stored::

    uv run python scripts/analysis/T04j_spread_hours.py

Per instrument and UTC hour: the median spread over the hour's bars divided by the instrument's
median over all bars (1.0 = typical), and the same for the first bar of each D-010 trading day (the
bar a daily strategy fills at: 00:00 UTC, or the Sunday bar that opens Monday).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

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
        overall = bars["spread"].median()
        by_hour = (
            bars.group_by(pl.col("ts").dt.hour().alias("utc_hour"))
            .agg((pl.col("spread").median() / overall).round(3).alias("rel"))
            .with_columns(pl.lit(sym).alias("symbol"))
        )
        frames.append(by_hour)
    out = pl.concat(frames).pivot(on="symbol", index="utc_hour", values="rel").sort("utc_hour")
    out.write_csv(OUT)
    pl.Config.set_tbl_rows(30)
    pl.Config.set_float_precision(2)
    print(out)


if __name__ == "__main__":
    main()
