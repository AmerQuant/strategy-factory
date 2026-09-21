"""T04l section 1: what the CUSIP evidence can say about each re-use candidate -- measured first.

Local only; reads the committed review CSVs and the raw ``NAME_CHANGE`` feed (read-only, D-028);
writes ``docs/reviews/T04l_cusip_coverage.csv``; changes nothing in the store::

    uv run python scripts/analysis/T04l_coverage.py

Candidates (D-705, D-708):

* **T04k kept** -- the 221 re-use candidates D-700 could not settle (`T04k_boundaries.csv`,
  outcome ``kept ...``), boundary = the T04k boundary date;
* **D-708 long gaps** -- every gap of ``relisting.gap_days`` or more **without** a price-level break
  in a current 1D or 1H reference (`T04h_long_gaps.csv`), boundary = the date the series resumes.

The feed carries a CUSIP only on a rename row (``old_symbol/old_cusip -> new_symbol/new_cusip``),
so a ticker has CUSIP evidence only where a holder renamed into or away from it. Per candidate:

* **before** the break: a rename *away* from the ticker before it resumes (the old holder leaving,
  as D-700 reads it), or a rename *into* it before the break starts;
* **after** the break: a rename *into* the ticker from the break start on (the new holder
  arriving), or a rename *away* after it resumes.

Coverage class: ``both`` (a CUSIP on each side -- the CUSIP can decide), ``before_only``,
``after_only``, ``none``. For ``both``: whether the CUSIPs are identical, share the six-character
issuer prefix, or differ in issuer.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.data.config import load_alpaca_config
from strategy_factory.data.download.rawfiles import raw_root

OUT = Path("docs") / "reviews"
BOUNDARIES = OUT / "T04k_boundaries.csv"
LONG_GAPS = OUT / "T04h_long_gaps.csv"
ISSUER = 6  # CUSIP issuer prefix length -- a property of the CUSIP format, not a threshold


def _feed() -> pl.DataFrame:
    path = raw_root() / load_alpaca_config().relisting.name_changes_file
    rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return pl.DataFrame(rows).with_columns(pl.col("process_date").str.to_date())


def _candidates() -> pl.DataFrame:
    kept = (
        pl.read_csv(BOUNDARIES, infer_schema_length=None)
        .filter(pl.col("outcome").str.starts_with("kept"))
        .select(
            "symbol",
            pl.lit("1D").alias("tf"),
            pl.lit("T04k kept").alias("source"),
            pl.col("boundary_date").str.to_date().alias("resumes"),
            pl.col("boundary_reason").alias("reason"),
            pl.col("name_verdict"),
        )
    )
    gaps = (
        pl.read_csv(LONG_GAPS, infer_schema_length=None)
        .filter(~pl.col("level_break"))
        .select(
            "symbol",
            "tf",
            pl.lit("D-708 long gap").alias("source"),
            pl.col("resumes").str.to_date(),
            pl.lit("gap_no_level_break").alias("reason"),
            pl.lit(None, pl.Utf8).alias("name_verdict"),
        )
    )
    return pl.concat([kept, gaps])


def _side(feed: pl.DataFrame, symbol: str, resumes: dt.date, gap_days: int | None) -> dict:
    start = resumes - dt.timedelta(days=gap_days) if gap_days else resumes
    away = feed.filter(pl.col("old_symbol") == symbol)
    into = feed.filter(pl.col("new_symbol") == symbol)
    before = pl.concat(
        [
            away.filter(pl.col("process_date") < resumes).select(
                pl.col("old_cusip").alias("cusip"), "process_date"
            ),
            into.filter(pl.col("process_date") < start).select(
                pl.col("new_cusip").alias("cusip"), "process_date"
            ),
        ]
    )
    after = pl.concat(
        [
            into.filter(pl.col("process_date") >= start).select(
                pl.col("new_cusip").alias("cusip"), "process_date"
            ),
            away.filter(pl.col("process_date") >= resumes).select(
                pl.col("old_cusip").alias("cusip"), "process_date"
            ),
        ]
    )
    b = sorted({c for c in before["cusip"].to_list() if c})
    a = sorted({c for c in after["cusip"].to_list() if c})
    cls = "both" if b and a else "before_only" if b else "after_only" if a else "none"
    relation = None
    if cls == "both":
        if set(b) & set(a):
            relation = "same_cusip"
        elif {x[:ISSUER] for x in b} & {x[:ISSUER] for x in a}:
            relation = "same_issuer"
        else:
            relation = "different_issuer"
    return {
        "rows_in_feed": away.height + into.height,
        "cusips_before": "|".join(b),
        "cusips_after": "|".join(a),
        "coverage": cls,
        "relation": relation,
    }


def main() -> None:
    feed = _feed()
    cands = _candidates()
    gaps = pl.read_csv(LONG_GAPS, infer_schema_length=None).select(
        "symbol", "tf", pl.col("resumes").str.to_date(), "gap_days"
    )
    cands = cands.join(gaps, on=["symbol", "tf", "resumes"], how="left")
    rows = [
        {**r, **_side(feed, r["symbol"], r["resumes"], r["gap_days"])}
        for r in cands.iter_rows(named=True)
    ]
    out = pl.DataFrame(rows).sort("source", "tf", "symbol")
    out.write_csv(OUT / "T04l_cusip_coverage.csv")

    print(
        f"feed rows {feed.height}; rows with a CUSIP change {feed.filter(pl.col('old_cusip') != pl.col('new_cusip')).height}"
    )
    print(out.group_by("source", "tf", "coverage").len().sort("source", "tf", "coverage"))
    print(out.filter(pl.col("coverage") == "both").group_by("source", "tf", "relation").len())
    print(
        "candidates with any feed row:",
        out.filter(pl.col("rows_in_feed") > 0).height,
        "of",
        out.height,
    )
    named = ["MBLY", "SE", "SNOW", "CTRA", "PCL", "Q", "CSRA", "AYA", "HAWK", "DOW", "EMC"]
    print(
        out.filter(pl.col("symbol").is_in(named))
        .select("symbol", "tf", "source", "resumes", "rows_in_feed", "coverage", "relation")
        .rows()
    )


if __name__ == "__main__":
    main()
