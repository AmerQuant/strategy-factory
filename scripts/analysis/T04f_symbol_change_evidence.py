"""T04f (D-383): evidence for every Alpaca NAME_CHANGE that touches the hourly universe.

Local only -- it reads `SFAC_RAW_ROOT` and the committed configs, writes no snapshot and
makes no network call. Regenerates `docs/reviews/T04f_symbol_changes_accounting.csv`::

    uv run python scripts/analysis/T04f_symbol_change_evidence.py [--out PATH]

**The test.** For each PIT ticker the builder would rename, follow the chain the way
`current_symbol` does (so the effective date is the one of the *hop actually taken*, not the
first row the feed happens to list for that ticker), then compare the two symbols' daily closes
on the trading days **strictly before** that date:

* >= 99.5 % identical  -> `rename_confirmed`, the same series.
* < 90 % identical      -> `different_company`.
* between the two       -> `inconclusive`; decide it by hand.
* destination has no prices at all -> `destination_no_data`.
* **no shared trading day before the change** -> `rename_confirmed_no_overlap`: there is nothing
  to compare, which is what a rename looks like when Alpaca stops serving the old ticker (`CDAY`,
  `FBHS`, `JEC` in the 2026-09-20 feed). It is a weaker verdict than `rename_confirmed` and is
  reported separately so it can be reviewed.

The two percentages are printed with every run and can be overridden (`--same-pct`, `--other-pct`);
they are the rule the supervisor confirms in P-68, not tuning knobs.

A mismatch alone does not settle it: the question is whether the **old** symbol's own series
covers its own index-membership window. When it does, the old row is real data and is kept
(the rename is rejected). When it does not -- Alpaca serves some other company under that
ticker and nothing for the membership period -- the old row is useless and the rename is
followed. `FI` is the only symbol in the 2026-09-20 feed of that second kind.

Rejections are written to `configs/universe/symbol_changes_manual.csv` as rows with an empty
`new_symbol` (see `build_symbol_changes`); this script only produces the evidence for them.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.data.download.alpaca_reference import read_changes_csv
from strategy_factory.data.download.rawfiles import raw_root

SPLIT_DIR = ("us_equity", "alpaca_sip_split")
CONFIGS = Path("configs") / "universe"
MONETA_MAP = Path("configs") / "costs" / "moneta" / "symbol_map.csv"
SAME_SERIES_PCT = 99.5  # at or above: the same series (D-383 / P-68, overridable on the CLI)
OTHER_SERIES_PCT = 90.0  # below: a different company (D-383 / P-68, overridable on the CLI)
OUT_DEFAULT = Path("docs") / "reviews" / "T04f_symbol_changes_accounting.csv"
PREVIOUS_REV = "docs/batch3-data"  # the 827-row universe as it was before T04f

COLUMNS = [
    "removed_symbol",
    "destination",
    "chain",
    "effective_date",
    "pit_membership",
    "pre_change_days",
    "pre_change_identical_pct",
    "post_change_identical_pct",
    "old_1D_range",
    "old_days_in_membership_window",
    "dest_1D_range",
    "dest_has_1H_raw",
    "dest_in_previous_universe",
    "moneta_target",
    "verdict",
    "action",
]


def daily_closes(root: Path, symbol: str) -> dict[str, float]:
    """date -> close from the latest version of every raw year file of ``symbol``."""
    folder = root.joinpath(*SPLIT_DIR, "1D", symbol)
    latest: dict[str, Path] = {}
    for f in sorted(folder.glob("*.parquet")):
        latest[f.name.split(".")[0]] = f  # "2026.v2.parquet" sorts after "2026.parquet"
    if not latest:
        return {}
    frame = pl.concat([pl.read_parquet(f).select(["t", "c"]) for f in latest.values()]).drop_nulls(
        "c"
    )
    return {t[:10]: c for t, c in zip(frame["t"].to_list(), frame["c"].to_list(), strict=True)}


def identical_pct(a: dict[str, float], b: dict[str, float], days: list[str]) -> float | None:
    """Share of ``days`` on which the two closes agree; ``None`` when there is nothing to compare."""
    if not days:
        return None
    same = sum(1 for d in days if b[d] != 0 and abs(a[d] / b[d] - 1) < 1e-6)
    return round(100 * same / len(days), 1)


def follow(
    symbol: str, by_old: dict[str, list[dict[str, str]]], since: str
) -> list[tuple[str, str]]:
    """The hops `current_symbol` would take: [(new_symbol, effective_date), ...]."""
    hops: list[tuple[str, str]] = []
    cur, when = symbol, since
    while len(hops) <= 20:
        nxt = [r for r in by_old.get(cur, []) if r["new_symbol"] and r["effective_date"] >= when]
        if not nxt:
            return hops
        step = min(nxt, key=lambda r: r["effective_date"])
        hops.append((step["new_symbol"], step["effective_date"]))
        cur, when = step["new_symbol"], step["effective_date"]
    raise ValueError(f"symbol-change chain too long from {symbol}")


def rows_for(
    root: Path,
    universe: Path,
    previous: Path | None,
    raw_feed: Path,
    same_pct: float = SAME_SERIES_PCT,
    other_pct: float = OTHER_SERIES_PCT,
) -> list[dict[str, Any]]:
    """One row per PIT ticker the **raw feed** renames, with the evidence for its verdict.

    The chain is followed on the raw feed, not on the generated `symbol_changes.csv`, so a
    rejected rename still gets the comparison that justifies rejecting it.
    """
    feed = [
        {
            "old_symbol": r["old_symbol"],
            "new_symbol": r["new_symbol"],
            "effective_date": str(r["process_date"])[:10],
        }
        for r in json.loads(raw_feed.read_text(encoding="utf-8"))
        if r.get("old_symbol") and r.get("new_symbol") and r["old_symbol"] != r["new_symbol"]
    ]
    by_old: dict[str, list[dict[str, str]]] = {}
    for r in feed:
        by_old.setdefault(r["old_symbol"], []).append(r)
    rejected = {
        r["old_symbol"]: r["source"]
        for r in read_changes_csv(CONFIGS / "symbol_changes_manual.csv")
        if not r["new_symbol"]
    }
    with universe.open(encoding="utf-8", newline="") as fh:
        current = {r["symbol"] for r in csv.DictReader(fh)}
    before: dict[str, dict[str, str]] = {}
    if previous is not None and previous.is_file():
        with previous.open(encoding="utf-8", newline="") as fh:
            before = {r["symbol"]: r for r in csv.DictReader(fh)}
    moneta: set[str] = set()
    if MONETA_MAP.is_file():
        with MONETA_MAP.open(encoding="utf-8", newline="") as fh:
            moneta = {r["research_symbol"] for r in csv.DictReader(fh)}

    out: list[dict[str, Any]] = []
    for sym, row in sorted(before.items()):
        first, last = row["first_member_date"], row["last_member_date"]
        hops = follow(sym, by_old, first or "0000-00-00")
        if not hops and sym not in rejected:
            continue  # untouched by the feed
        dest = hops[-1][0] if hops else sym
        eff = hops[0][1] if hops else (by_old.get(sym, [{}])[0].get("effective_date", ""))
        co, cd = daily_closes(root, sym), daily_closes(root, dest)
        common = sorted(set(co) & set(cd))
        pre = [d for d in common if d < eff]
        post = [d for d in common if d >= eff]
        pre_pct, post_pct = identical_pct(co, cd, pre), identical_pct(co, cd, post)
        in_window = [d for d in co if first <= d <= (last or "9999-99-99")]
        if not cd:
            verdict = "destination_no_data"
        elif pre_pct is None:
            verdict = "rename_confirmed_no_overlap"  # nothing to compare; see the module docstring
        elif pre_pct >= same_pct:
            verdict = "rename_confirmed"
        elif pre_pct < other_pct:
            verdict = "different_company"
        else:
            verdict = "inconclusive"
        if verdict in ("different_company", "destination_no_data") and not in_window:
            verdict = "old_symbol_has_no_data_in_its_membership_window"
        if sym in rejected:
            action = "keep old row, drop destination (rejected in symbol_changes_manual.csv)"
        elif sym in current:
            action = "kept (the feed does not move it)"
        else:
            action = "exclude old row, keep destination"
        out.append(
            {
                "removed_symbol": sym,
                "destination": dest,
                "chain": " ".join(f"{a}@{b}" for a, b in hops) or "-",
                "effective_date": eff,
                "pit_membership": f"{first}..{last}",
                "pre_change_days": len(pre),
                "pre_change_identical_pct": pre_pct,
                "post_change_identical_pct": post_pct,
                "old_1D_range": f"{min(co)}..{max(co)}" if co else "-",
                "old_days_in_membership_window": len(in_window),
                "dest_1D_range": f"{min(cd)}..{max(cd)}" if cd else "-",
                "dest_has_1H_raw": root.joinpath(*SPLIT_DIR, "1H", dest).is_dir(),
                "dest_in_previous_universe": dest in before,
                "moneta_target": sym in moneta,
                "verdict": verdict,
                "action": action,
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--same-pct", type=float, default=SAME_SERIES_PCT)
    ap.add_argument("--other-pct", type=float, default=OTHER_SERIES_PCT)
    ap.add_argument("--universe", type=Path, default=CONFIGS / "us_equity_hourly.csv")
    ap.add_argument(
        "--previous",
        type=Path,
        help="The hourly universe as it was before T04f (default: read it from git).",
    )
    ap.add_argument(
        "--raw",
        type=Path,
        help="Raw NAME_CHANGE answer (default: the newest under raw/reference/alpaca).",
    )
    ap.add_argument(
        "--previous-rev",
        default=PREVIOUS_REV,
        help=f"git revision holding that file (default: {PREVIOUS_REV}).",
    )
    args = ap.parse_args()
    previous = args.previous
    if previous is None:
        import subprocess

        blob = subprocess.run(
            ["git", "show", f"{args.previous_rev}:{args.universe.as_posix()}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 - kept until the script exits
            "w", suffix=".csv", encoding="utf-8", delete=False
        )
        with tmp:
            tmp.write(blob)
        previous = Path(tmp.name)
    root = raw_root()
    raw_feed = args.raw
    if raw_feed is None:
        candidates = sorted(
            f
            for f in (root / "reference" / "alpaca" / "corporate_actions").glob(
                "name_changes_*.json"
            )
            if not f.name.endswith(".manifest.json")
        )
        if not candidates:
            raise SystemExit(
                "no raw NAME_CHANGE file; run `sfac data reference alpaca-symbol-changes`"
            )
        raw_feed = candidates[-1]
    rows = rows_for(root, args.universe, previous, raw_feed, args.same_pct, args.other_pct)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print(
        f"{len(rows)} rows -> {args.out}  (same >= {args.same_pct} %, different < {args.other_pct} %)"
    )
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    print(f"generated {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
