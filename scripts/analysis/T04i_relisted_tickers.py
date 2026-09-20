"""T04i (D-383, amended by **D-398**): frozen stretches, re-used tickers and their boundaries.

Local only -- reads `SFAC_RAW_ROOT`, writes no snapshot::

    uv run python scripts/analysis/T04i_relisted_tickers.py [--out PATH] [--verdicts PATH]

Sweeps every symbol of `configs/universe/us_equity_daily.csv` with
`strategy_factory.data.relisting` and writes two artefacts:

* `docs/reviews/T04i_relisted_candidates.csv` -- one row per frozen stretch or trading gap, with
  the symbol's **boundary** (D-398): the date its honest history starts;
* `docs/reviews/T04i_relisting_verdicts.csv` -- one row per affected symbol: verdict, boundary,
  the dropped span and what is left.

D-398 keeps the symbol in every case but one, so the exclusion file
`configs/universe/us_equity_daily_excluded.csv` holds only the symbols whose boundary cannot be
placed from the series (verdict `exclude_boundary_unidentifiable`). `--write-exclusions` writes it.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import polars as pl

from strategy_factory.data.config import load_alpaca_config, load_known_splits
from strategy_factory.data.download.rawfiles import raw_root
from strategy_factory.data.relisting import (
    EXCLUDE,
    TRIM,
    SeriesVerdict,
    analyse_series,
    looks_like_reverse_split,
)

DAILY_DIR = ("us_equity", "alpaca_sip_split", "1D")
UNIVERSE = Path("configs") / "universe" / "us_equity_daily.csv"
OUT_DEFAULT = Path("docs") / "reviews" / "T04i_relisted_candidates.csv"
VERDICTS_DEFAULT = Path("docs") / "reviews" / "T04i_relisting_verdicts.csv"
EXCLUDED = Path("configs") / "universe" / "us_equity_daily_excluded.csv"
MONETA_MAP = Path("configs") / "costs" / "moneta" / "symbol_map.csv"
MONETA_OVERRIDES = Path("configs") / "costs" / "moneta" / "symbol_overrides.csv"
COLUMNS = [
    "symbol",
    "reason",
    "moneta_target",
    "boundary_date",
    "verdict",
    "last_date_before_gap",
    "first_date_after_gap",
    "gap_days",
    "stale_bars",
    "close_before",
    "close_after",
    "ratio",
]
VERDICT_COLUMNS = [
    "symbol",
    "verdict",
    "moneta_target",
    "boundary_date",
    "boundary_reason",
    "dropped_from",
    "dropped_to",
    "dropped_bars",
    "frozen_stretches",
    "frozen_bars_cut",
    "kept_bars",
    "kept_from",
    "kept_to",
    "reverse_split_suspect",
]


def latest_year_files(folder: Path) -> list[Path]:
    latest: dict[str, Path] = {}
    for f in sorted(folder.glob("*.parquet")):
        latest[f.name.split(".")[0]] = f
    return list(latest.values())


def moneta_targets() -> set[str]:
    """Research symbols the T06b broker mapping points at -- kept under D-388, never dropped."""
    out: set[str] = set()
    for path in (MONETA_MAP, MONETA_OVERRIDES):
        if path.is_file():
            with path.open(encoding="utf-8", newline="") as fh:
                out |= {
                    r["research_symbol"] for r in csv.DictReader(fh) if r.get("research_symbol")
                }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--verdicts", type=Path, default=VERDICTS_DEFAULT)
    ap.add_argument("--gap-days", type=int, help="default: relisting.gap_days")
    ap.add_argument("--frozen-sessions", type=int, help="default: relisting.frozen_min_sessions")
    ap.add_argument("--symbols", help="Comma-separated subset (default: the daily universe).")
    ap.add_argument(
        "--write-exclusions",
        action="store_true",
        help=f"write {EXCLUDED} from the symbols whose boundary cannot be placed (D-398 (4)).",
    )
    args = ap.parse_args()

    root, cfg = raw_root(), load_alpaca_config()
    gap_days = args.gap_days if args.gap_days is not None else cfg.relisting.gap_days
    frozen = (
        args.frozen_sessions
        if args.frozen_sessions is not None
        else cfg.relisting.frozen_min_sessions
    )
    daily_dir = root.joinpath(*DAILY_DIR)
    splits = {
        k.symbol: frozenset({k.date}) for k in load_known_splits(cfg.split_check.known_splits_file)
    }
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        with UNIVERSE.open(encoding="utf-8", newline="") as fh:
            symbols = [r["symbol"] for r in csv.DictReader(fh)]

    # D-388: a symbol that is a Moneta mapping target is KEPT and reported, never dropped.
    moneta = moneta_targets()

    rows: list[dict[str, object]] = []
    verdicts: list[SeriesVerdict] = []
    for i, sym in enumerate(symbols, 1):
        files = latest_year_files(daily_dir / sym)
        if not files:
            continue
        frame = (
            pl.concat([pl.read_parquet(f).select("t", "h", "l", "c") for f in files])
            .drop_nulls("c")
            .with_columns(pl.col("t").str.slice(0, 10).str.to_date().alias("d"))
            .sort("d")
        )
        if frame.height < 2:
            continue
        verdict = analyse_series(
            sym,
            frame["d"].to_list(),
            frame["h"].to_list(),
            frame["l"].to_list(),
            frame["c"].to_list(),
            cfg.split_check.jump_threshold,
            splits.get(sym, frozenset()),
            gap_days,
            frozen,
        )
        if not verdict.rows:
            continue
        verdicts.append(verdict)
        for row in verdict.rows:
            row["moneta_target"] = sym in moneta
            row["boundary_date"] = verdict.boundary_date
            row["verdict"] = verdict.verdict
        rows += verdict.rows
        if i % 500 == 0:
            print(f"  {i}/{len(symbols)} symbols, {len(rows)} rows", flush=True)

    rows.sort(key=lambda r: abs(float(r["ratio"]) - 1.0), reverse=True)  # worst break first
    _write(args.out, COLUMNS, rows)
    verdicts.sort(key=lambda v: (-v.dropped_bars, v.symbol))
    _write(
        args.verdicts,
        VERDICT_COLUMNS,
        [
            {
                **v.as_row(),
                "moneta_target": v.symbol in moneta,
                "reverse_split_suspect": _reverse_split_suspect(v),
            }
            for v in verdicts
        ],
    )

    excluded = [v for v in verdicts if v.verdict == EXCLUDE]
    if args.write_exclusions:
        _write(
            EXCLUDED,
            ["symbol", "reason", "evidence"],
            [
                {
                    "symbol": v.symbol,
                    "reason": "boundary_unidentifiable",
                    "evidence": (
                        f"D-398 (4): {v.boundary_reason} at the end of the series; "
                        f"no real bar after it ({v.dropped_from}..{v.dropped_to}, "
                        f"{v.dropped_bars} bars, {v.frozen_stretches} frozen stretches)"
                    ),
                }
                for v in excluded
            ],
        )
        print(f"{len(excluded)} exclusions -> {EXCLUDED}")

    suspects = [v for v in verdicts if _reverse_split_suspect(v)]
    by_verdict: dict[str, int] = {}
    for v in verdicts:
        by_verdict[v.verdict] = by_verdict.get(v.verdict, 0) + 1
    print(f"\n{len(symbols)} symbols scanned, {len(rows)} rows over {len(verdicts)} symbols")
    print(f"  thresholds: frozen >= {frozen} sessions, gap >= {gap_days} days")
    for name, count in sorted(by_verdict.items(), key=lambda kv: -kv[1]):
        print(f"  {name:34} {count:5}")
    print(f"  moneta targets among them: {sum(1 for v in verdicts if v.symbol in moneta)}")
    print(f"  reverse-split suspects among the trims (P-74): {len(suspects)}")
    for v in verdicts[:15]:
        print(
            f"  {v.symbol:6} {v.verdict:34} boundary {v.boundary_date or '-':10} "
            f"dropped {v.dropped_bars:5} bars, kept {v.kept_bars:5}"
        )


def _reverse_split_suspect(verdict: SeriesVerdict) -> bool:
    """P-74: the boundary-setting break of a trim looks like an unadjusted reverse split.

    Only the row that actually set the boundary counts -- a padded stretch elsewhere in the
    series says nothing about why the history was cut.
    """
    if verdict.verdict != TRIM:
        return False
    breaks = [
        r
        for r in verdict.rows
        if r["reason"] in ("stale_run", "trading_gap", "pre_listing_padding")
        and str(r["first_date_after_gap"]) < verdict.boundary_date
    ]
    if not breaks:
        return False
    last = max(breaks, key=lambda r: str(r["first_date_after_gap"]))
    return last["reason"] != "pre_listing_padding" and looks_like_reverse_split(
        float(last["ratio"])
    )


def _write(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, columns, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
