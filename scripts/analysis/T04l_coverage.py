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
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.data.config import load_alpaca_config
from strategy_factory.data.download.alpaca_reference import action_date, latest_action_files
from strategy_factory.data.download.rawfiles import raw_root

OUT = Path("docs") / "reviews"
BOUNDARIES = OUT / "T04k_boundaries.csv"
LONG_GAPS = OUT / "T04h_long_gaps.csv"
ISSUER = 6  # CUSIP issuer prefix length -- a property of the CUSIP format, not a threshold

#: (symbol field, cusip field, role) per answer key; role: "id" (who held the ticker on the date),
#: "into"/"away" (a rename into / away from the ticker), "ceased" (the security ended).
FIELDS: dict[str, list[tuple[str, str, str]]] = {
    "name_changes": [("old_symbol", "old_cusip", "away"), ("new_symbol", "new_cusip", "into")],
    "cash_dividends": [("symbol", "cusip", "id")],
    "stock_dividends": [("symbol", "cusip", "id")],
    "forward_splits": [("symbol", "cusip", "id")],
    "reverse_splits": [("symbol", "old_cusip", "id_before"), ("symbol", "new_cusip", "id")],
    "unit_splits": [
        ("old_symbol", "old_cusip", "away"),
        ("new_symbol", "new_cusip", "into"),
        ("alternate_symbol", "alternate_cusip", "into"),
    ],
    "spin_offs": [("source_symbol", "source_cusip", "id"), ("new_symbol", "new_cusip", "into")],
    "rights_distributions": [("source_symbol", "source_cusip", "id")],
    "cash_mergers": [
        ("acquiree_symbol", "acquiree_cusip", "ceased"),
        ("acquirer_symbol", "acquirer_cusip", "id"),
    ],
    "stock_mergers": [
        ("acquiree_symbol", "acquiree_cusip", "ceased"),
        ("acquirer_symbol", "acquirer_cusip", "id"),
    ],
    "stock_and_cash_mergers": [
        ("acquiree_symbol", "acquiree_cusip", "ceased"),
        ("acquirer_symbol", "acquirer_cusip", "id"),
    ],
    "worthless_removals": [("symbol", "cusip", "ceased")],
    "redemptions": [("symbol", "cusip", "ceased")],
}


def _events() -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    """symbol -> [{type, role, cusip, date}] with a CUSIP; and rows without one, per type."""
    folder = raw_root() / "reference" / "alpaca" / "corporate_actions"
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    no_cusip: dict[str, int] = defaultdict(int)
    for key, path in latest_action_files(folder).items():
        spec = FIELDS.get(key)
        if spec is None:
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            date = action_date(row)
            for sym_f, cus_f, role in spec:
                sym, cus = row.get(sym_f), row.get(cus_f)
                if not sym:
                    continue
                if not cus:
                    no_cusip[key] += 1
                    continue
                by_symbol[str(sym)].append(
                    {"type": key, "role": role, "cusip": str(cus), "date": date}
                )
    return by_symbol, no_cusip


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


def _classify(events: list[dict[str, Any]], resumes: dt.date, window: int) -> dict[str, Any]:
    r = resumes.isoformat()
    into_from = (resumes - dt.timedelta(days=window)).isoformat()
    before: dict[str, set[str]] = defaultdict(set)  # cusip -> types
    after: dict[str, set[str]] = defaultdict(set)
    ceased: set[str] = set()
    # Rows re-keyed to a later ticker: Alpaca files some rows under the ticker a security took
    # LATER (measured: ~5 % of dividends before a same-CUSIP rename, CTRA/COG, CIVI/BCEI). A row of a
    # CUSIP under this ticker dated before that CUSIP renamed INTO it is not evidence of who held
    # the ticker then, and is dropped.
    arrived: dict[str, str] = {}
    for e in events:
        if e["role"] == "into":
            arrived[e["cusip"]] = min(arrived.get(e["cusip"], e["date"]), e["date"])
    for e in events:
        d, role = e["date"], e["role"]
        if role not in ("into", "away") and e["cusip"] in arrived and d < arrived[e["cusip"]]:
            continue
        if role in ("into", "id"):
            # the new holder may act under the ticker just before it trades (a rename into it, or
            # an acquirer row filed under the new ticker, as Coterra/Cimarex on CTRA)
            side = after if d >= into_from else before
        elif role == "id_before":  # a reverse split's old CUSIP held the ticker until that date
            side = before if d <= r else after
        else:  # "away", "ceased": the old holder leaving
            side = before if d < r else after
        side[e["cusip"]].add(e["type"])
        if role == "ceased" and d < r:
            ceased.add(e["type"])
    b, a = set(before), set(after)
    cls = "both" if b and a else "before_only" if b else "after_only" if a else "none"
    relation = None
    if cls == "both":
        if b & a:
            relation = "same_cusip"
        elif {x[:ISSUER] for x in b} & {x[:ISSUER] for x in a}:
            relation = "same_issuer"
        else:
            relation = "different_issuer"
    return {
        "coverage": cls,
        "relation": relation,
        "cusips_before": "|".join(sorted(b)),
        "cusips_after": "|".join(sorted(a)),
        "types_before": "|".join(sorted({t for ts in before.values() for t in ts})),
        "types_after": "|".join(sorted({t for ts in after.values() for t in ts})),
        "ceased_before": "|".join(sorted(ceased)),
    }


def main() -> None:
    window = load_alpaca_config().relisting.rename_window_days
    events, no_cusip = _events()
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
            rest = [e for e in events.get(r["symbol"], []) if e["type"] != t]
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
