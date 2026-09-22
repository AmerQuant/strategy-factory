"""T04l section 1: what the CUSIP evidence can say about each re-use candidate -- measured first.

Local only; reads the committed review CSVs and the raw corporate-action files (read-only,
D-028; the **latest version** of each answer key); writes ``docs/reviews/T04l_cusip_coverage.csv``
and ``docs/reviews/T04l_coverage_by_type.csv``; changes nothing in the store::

    uv run python scripts/analysis/T04l_coverage.py

Candidates (D-705, D-708): the 221 re-use candidates T04k kept (`T04k_boundaries.csv`, outcome
``kept ...``) and every gap >= ``relisting.gap_days`` without a price-level break in a current 1D or
1H reference (`T04h_long_gaps.csv`). ``resumes`` = the first bar after the break.

**Evidence** (D-710): every corporate-action row that names the ticker **with a CUSIP** -- a row
without one is not identity evidence and is counted apart. A row is on the **before** side when
dated before the series resumes, on the **after** side from then on; a rename **into** the ticker,
or any row naming the ticker's holder, counts as after from ``relisting.rename_window_days`` before
the resumption (the new holder may act under the ticker just before it trades, as D-700 reads it);
a rename **away** and a cessation stay on the before side until the resumption. A **cessation** -- the ticker's security
acquired (cash/stock/stock-and-cash merger, ``acquiree_*``), removed as worthless, or redeemed --
before the resumption is recorded separately: it says the old security is gone.

Per candidate: ``both`` (a CUSIP on each side; the relation decides: same CUSIP, same issuer = the
first six characters, or different issuer), ``before_only``, ``after_only``, ``none``.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.data.config import load_alpaca_config
from strategy_factory.data.cusip_evidence import FIELDS, Event, classify, load_events
from strategy_factory.data.download.rawfiles import raw_root

OUT = Path("docs") / "reviews"
BOUNDARIES = OUT / "T04k_boundaries.csv"
LONG_GAPS = OUT / "T04h_long_gaps.csv"
CA_DIR = ("reference", "alpaca", "corporate_actions")


def _candidates() -> pl.DataFrame:
    kept = (
        pl.read_csv(BOUNDARIES, infer_schema_length=None)
        .filter(pl.col("outcome").str.starts_with("kept"))
        .select(
            "symbol",
            pl.lit("1D").alias("tf"),
            pl.lit("T04k kept").alias("source"),
            pl.col("boundary_date").str.to_date().alias("resumes"),
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
            pl.lit(None, pl.Utf8).alias("name_verdict"),
        )
    )
    return pl.concat([kept, gaps])


def _classify(events: list[Event], resumes: dt.date, window: int) -> dict[str, Any]:
    """The library's classification (``data/cusip_evidence.py``, D-712 rules) as a table row."""
    ev = classify(events, resumes, window)
    return {
        "coverage": ev.coverage,
        "relation": ev.relation,
        "cusips_before": "|".join(ev.before),
        "cusips_after": "|".join(ev.after),
        "types_before": "|".join(ev.types_before),
        "types_after": "|".join(ev.types_after),
        "ceased_before": "|".join(ev.ceased_before),
        "dropped_rekeyed": ev.dropped_rekeyed,
    }


def main() -> None:
    window = load_alpaca_config().relisting.rename_window_days
    events, no_cusip = load_events(raw_root().joinpath(*CA_DIR))
    cands = _candidates()
    rows = [
        {**c, **_classify(events.get(c["symbol"], []), c["resumes"], window)}
        for c in cands.iter_rows(named=True)
    ]
    out = pl.DataFrame(rows).sort("source", "tf", "symbol")
    out.write_csv(OUT / "T04l_cusip_coverage.csv")

    # per action type: on how many candidate rows it gives a before / after CUSIP, and on how many
    # decided ("both") rows it is part of the evidence; "only" = the decision needs that type
    types = sorted(FIELDS)
    per_type = []
    for t in types:
        has_b = out["types_before"].str.split("|").list.contains(t)
        has_a = out["types_after"].str.split("|").list.contains(t)
        both = out.filter((pl.col("coverage") == "both") & (has_b | has_a))
        only = 0
        for r in both.iter_rows(named=True):
            rest = [e for e in events.get(r["symbol"], []) if e.type != t]
            if _classify(rest, r["resumes"], window)["coverage"] != "both":
                only += 1
        per_type.append(
            {
                "type": t,
                "rows_without_cusip": no_cusip.get(t, 0),
                "candidates_before": int(has_b.sum()),
                "candidates_after": int(has_a.sum()),
                "candidates_ceased_before": int(
                    out["ceased_before"].str.split("|").list.contains(t).sum()
                ),
                "part_of_decided": both.height,
                "decided_only_with_it": only,
            }
        )
    by_type = pl.DataFrame(per_type)
    by_type.write_csv(OUT / "T04l_coverage_by_type.csv")

    pl.Config.set_tbl_rows(30)
    pl.Config.set_tbl_cols(12)
    pl.Config.set_tbl_width_chars(220)
    print(by_type)
    print(out.group_by("source", "tf", "coverage").len().sort("source", "tf", "coverage"))
    print(out.filter(pl.col("coverage") == "both").group_by("relation").len().sort("relation"))
    decided = out.filter(pl.col("coverage") == "both")
    ceased_only = out.filter((pl.col("coverage") != "both") & (pl.col("ceased_before") != ""))
    print(f"rows: {out.height}; decided by CUSIP on both sides: {decided.height}")
    print(f"not decided, but the old security ceased before the break: {ceased_only.height}")
    sym = out.group_by("symbol").agg(
        (pl.col("coverage") == "both").all().alias("all_decided"),
        (pl.col("coverage") == "both").any().alias("any_decided"),
    )
    print(
        f"symbols: {sym.height}; every row decided: {sym['all_decided'].sum()}; "
        f"unsettled (some row undecided): {sym.height - sym['all_decided'].sum()}"
    )
    long_1d = out.filter((pl.col("source") == "D-708 long gap") & (pl.col("tf") == "1D"))
    long_1h = out.filter((pl.col("source") == "D-708 long gap") & (pl.col("tf") == "1H"))
    print(
        f"D-708 long gaps decided: 1D {(long_1d['coverage'] == 'both').sum()} of {long_1d.height}, "
        f"1H {(long_1h['coverage'] == 'both').sum()} of {long_1h.height}"
    )
    named = ["MBLY", "SE", "SNOW", "CTRA", "PCL", "Q", "CSRA", "AYA", "HAWK", "DOW", "EMC"]
    print(
        out.filter(pl.col("symbol").is_in(named))
        .select("symbol", "tf", "resumes", "coverage", "relation", "ceased_before")
        .rows()
    )


if __name__ == "__main__":
    main()
