"""T04j plan: what the Dukascopy h1 raw set actually covers (D-026).

Local only; reads ``SFAC_RAW_ROOT/fx_metals_cfd/dukascopy/h1`` (read-only, D-028) and
``configs/universe/dukascopy.csv``; writes ``docs/reviews/T04j_raw_coverage.csv``; changes nothing::

    uv run python scripts/analysis/T04j_coverage.py

Per instrument and side (bid / ask): the month files present (latest version of each month), the
expected months from ``h1_start`` to the last complete month, missing and empty months, rows (from
each manifest), the months present on one side only, and the newest ``written_at`` -- which says
whether a download may still be running.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.data.config import load_dukascopy_config
from strategy_factory.data.download.rawfiles import MANIFEST_SUFFIX, raw_root, version_of

OUT = Path("docs") / "reviews" / "T04j_raw_coverage.csv"
UNIVERSE = Path("configs") / "universe" / "dukascopy.csv"


def _months(start: dt.date, end: dt.date) -> list[str]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _side(folder: Path) -> dict[str, dict[str, Any]]:
    """month -> manifest of the latest version of that month's file."""
    latest: dict[str, tuple[int, Path]] = {}
    if not folder.is_dir():
        return {}
    for f in folder.glob("*.csv.gz"):
        base, n = version_of(f, ".csv.gz")
        if base not in latest or n > latest[base][0]:
            latest[base] = (n, f)
    out: dict[str, dict[str, Any]] = {}
    for month, (_, f) in latest.items():
        m = f.with_name(f.name + MANIFEST_SUFFIX)
        out[month] = json.loads(m.read_text(encoding="utf-8")) if m.is_file() else {}
    return out


def main() -> None:
    cfg = load_dukascopy_config()
    root = raw_root() / "fx_metals_cfd" / "dukascopy" / "h1"
    today = dt.date.today()
    last_complete = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    expected = _months(cfg.h1_start, last_complete)
    universe = pl.read_csv(UNIVERSE)
    rows = []
    for inst, sym, cls in universe.select("instrument_id", "symbol", "asset_class").rows():
        bid, ask = _side(root / sym / "bid"), _side(root / sym / "ask")
        both = sorted(set(bid) & set(ask))
        written = [m.get("written_at", "") for side in (bid, ask) for m in side.values()]
        rows.append(
            {
                "symbol": sym,
                "asset_class": cls,
                "bid_months": len(bid),
                "ask_months": len(ask),
                "first": min(both) if both else "",
                "last": max(both) if both else "",
                "missing_months": len([m for m in expected if m not in bid or m not in ask]),
                "one_sided_months": len(set(bid) ^ set(ask)),
                "empty_months": sum(1 for m in both if (bid[m].get("row_count") or 0) == 0),
                "bid_rows": sum(int(v.get("row_count") or 0) for v in bid.values()),
                "ask_rows": sum(int(v.get("row_count") or 0) for v in ask.values()),
                "newest_write": max(written) if written else "",
                "complete": bool(both) and all(m in bid and m in ask for m in expected),
            }
        )
    out = pl.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.write_csv(OUT)
    pl.Config.set_tbl_rows(40)
    pl.Config.set_tbl_cols(14)
    pl.Config.set_tbl_width_chars(220)
    print(f"expected months per instrument: {len(expected)} ({expected[0]} .. {expected[-1]})")
    print(out)
    print(
        f"instruments complete {int(out['complete'].sum())} of {out.height}; "
        f"with any file {int((out['bid_months'] + out['ask_months'] > 0).sum())}; "
        f"newest write {out['newest_write'].max()}"
    )


if __name__ == "__main__":
    main()
