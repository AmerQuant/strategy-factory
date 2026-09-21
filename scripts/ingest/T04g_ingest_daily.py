"""T04g: ingest the Alpaca 1D raw store into snapshots, in chunks (D-385).

Local only -- no network (D-031). Reads `SFAC_RAW_ROOT`, writes `SFAC_DATA_ROOT`::

    uv run python scripts/ingest/T04g_ingest_daily.py [--chunk 250] [--limit N] [--dry-run]

One `sfac data ingest alpaca` invocation per chunk, each appended to
`<SFAC_DATA_ROOT>/_logs/T04g_ingest_1D.log` with a timestamp, so an interrupted run is simply
re-run: the operation is idempotent (identical content returns the stored snapshot, `register` is
a no-op for a known key, `set_reference` returns early).

The symbol list is `configs/universe/us_equity_daily.csv` **minus**
`configs/universe/us_equity_daily_excluded.csv` (D-383 as amended by D-398; T04i wrote that file
empty, so today nothing is excluded). Both are passed to the CLI, which does the subtraction --
no symbol is hard-coded here.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
from pathlib import Path

from strategy_factory.data.store import data_root

UNIVERSE = Path("configs") / "universe" / "us_equity_daily.csv"
EXCLUDED = Path("configs") / "universe" / "us_equity_daily_excluded.csv"
LOG_SUBDIR = "_logs"
LOG_NAME = "T04g_ingest_1D.log"


def read_symbols(path: Path, column: str = "symbol") -> list[str]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [r[column].strip() for r in csv.DictReader(fh) if r.get(column)]


def chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chunk", type=int, default=250, help="symbols per invocation (D-385)")
    ap.add_argument("--limit", type=int, help="only the first N symbols (a smoke run)")
    ap.add_argument("--timeframe", default="1D")
    ap.add_argument("--dry-run", action="store_true", help="print the chunks, run nothing")
    args = ap.parse_args()

    symbols = read_symbols(UNIVERSE)
    excluded = set(read_symbols(EXCLUDED))
    todo = [s for s in symbols if s not in excluded]
    if args.limit:
        todo = todo[: args.limit]
    groups = chunks(todo, args.chunk)
    print(
        f"{len(symbols)} in the universe, {len(excluded)} excluded, {len(todo)} to ingest "
        f"in {len(groups)} chunk(s) of {args.chunk}"
    )
    if args.dry_run:
        for i, g in enumerate(groups, 1):
            print(f"  chunk {i:>3}: {len(g):>4} symbols  {g[0]} .. {g[-1]}")
        return 0

    log_path = data_root() / LOG_SUBDIR / LOG_NAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    failed_chunks: list[int] = []
    started = dt.datetime.now(dt.UTC)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n=== T04g {args.timeframe} ingest started {started.isoformat()} ===\n")
        for i, group in enumerate(groups, 1):
            t0 = dt.datetime.now(dt.UTC)
            cmd = [
                "uv", "run", "sfac", "data", "ingest", "alpaca",
                "--timeframe", args.timeframe,
                "--symbols", ",".join(group),
                "--set-reference",
            ]  # fmt: skip
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            took = (dt.datetime.now(dt.UTC) - t0).total_seconds()
            tail = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
            counts = [ln for ln in tail if " symbols: " in ln]
            summary = counts[-1] if counts else (tail[-1] if tail else "(no output)")
            line = (
                f"{t0.isoformat(timespec='seconds')}  chunk {i}/{len(groups)}  "
                f"{group[0]}..{group[-1]}  {len(group)} symbols  rc={proc.returncode}  "
                f"{took:.1f}s  {summary}"
            )
            print(line, flush=True)
            log.write(line + "\n")
            for ln in tail:
                if "unadjusted" in ln or "excluded:" in ln or "FAILED" in ln:
                    log.write(f"    {ln}\n")
            if proc.stderr:
                log.write("".join(f"    stderr: {ln}\n" for ln in proc.stderr.splitlines()[-20:]))
            log.flush()
            if proc.returncode != 0:
                failed_chunks.append(i)
        total = (dt.datetime.now(dt.UTC) - started).total_seconds()
        log.write(
            f"=== finished in {total / 60:.1f} min, {len(failed_chunks)} chunk(s) rc!=0 ===\n"
        )
    print(f"\n{len(groups)} chunk(s) in {total / 60:.1f} min; rc!=0 for chunks {failed_chunks}")
    print(f"log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
