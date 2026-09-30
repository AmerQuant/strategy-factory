"""T04j: ingest every Dukascopy instrument over its D-661 window, and re-derive it when a gap closes.

The single resume command while the download runs (D-657, D-661). Local only, no network (D-031);
run from the stream B worktree, as often as the download progresses::

    uv run python scripts/pilots/T04j_resume.py              # measure, ingest, derive, report
    uv run python scripts/pilots/T04j_resume.py --dry-run    # windows, state and D-717 only
    uv run python scripts/pilots/T04j_resume.py --symbols EURUSD,USDCHF   # only these

Only **settled** raw months are read (``rawfiles.is_settled``: the data file and its manifest
written, no ``.partial``), so a month the download is still writing is never read. Per instrument,
in the task file's order (``docs/tasks/T04j_dukascopy_ingest.md``):

1. **The window (D-661):** the longest contiguous complete run of months ending at the last complete
   month. No window: it waits (an instrument already ingested stays ingested).
2. **State** (``data.window_state.reference_state``): *ingested* -- nothing to do, so a re-run
   writes nothing; *incomplete* -- the 1D or a quality report is missing, derive without a new
   ingest; *absent*, *pilot* (hash version 1, re-ingested with ``--rehash``) or *grown* (a gap
   closed and the window now starts earlier: re-derived as a new versioned snapshot, D-661;
   nothing is overwritten) -- ingest. A new month at the end of the window does not re-derive.
3. **D-008:** measured on the window's bars; a window too short to split waits (D-661).
4. **D-717:** the defect families are re-measured over the window of every instrument about to be
   ingested (``scripts/analysis/T04j_defects.py``). **An instrument with any family present is held
   and nothing is written for it** (per instrument, D-672); the others proceed. A bar listed in
   ``verified_events`` (D-672) is reported and is not a stop.
5. **Ingest 1H** with ``--set-reference`` (a pilot with ``--rehash``, event note ``rehash v1→v2``)
   and ``--expect-window`` = the window D-717 measured: if the download moved it in between, the
   ingest refuses that instrument and writes nothing, so D-717 always covers what is written.
6. **Build 1D** (D-010, D-032): ``sfac data resample --from 1H --to 1D --set-reference``, once.
7. **Quality** for both snapshots, then ``sfac costs show`` (the 1H development segment, D-523).

Writes ``docs/reviews/T04j_instrument_status.csv`` (per instrument: state, window, the gap that
bounds it; not with ``--dry-run`` or ``--symbols``) and prints the same summary. Exit 0 when every
step ran; 1 when an instrument was held by D-717 (raise it); 2 when a step failed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.cli import utf8_output
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import load_dukascopy_config
from strategy_factory.data.coverage import Window, dukascopy_coverage_frame, dukascopy_windows
from strategy_factory.data.download.dukascopy import Instrument, load_instruments
from strategy_factory.data.download.rawfiles import raw_root
from strategy_factory.data.window_state import reference_state

REPO = Path(__file__).resolve().parents[2]
STATUS = REPO / "docs" / "reviews" / "T04j_instrument_status.csv"
DEFECTS = REPO / "scripts" / "analysis" / "T04j_defects.py"
INGEST = ("absent", "pilot", "grown")


def _defects_module() -> Any:
    spec = importlib.util.spec_from_file_location("T04j_defects", DEFECTS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sfac(*args: str) -> int:
    """One ``sfac`` command in a child process (its output goes straight to this console)."""
    print(f"\n$ sfac {' '.join(args)}", flush=True)
    cmd = [sys.executable, "-m", "strategy_factory.cli", *args]
    return subprocess.run(cmd, check=False).returncode


def _span(w: Window | None) -> str:
    return f"{w.first}..{w.last}" if w is not None and w.first else "-"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="Windows, state and D-717 only.")
    parser.add_argument(
        "--symbols", help="Comma-separated symbols to consider (default: every instrument)."
    )
    args = parser.parse_args(argv)
    utf8_output()

    cfg = load_dukascopy_config()
    insts: list[Instrument] = load_instruments(cfg.universe_file)
    if args.symbols:
        wanted = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}
        unknown = wanted - {i.symbol for i in insts}
        if unknown:
            parser.error(f"not in the Dukascopy universe: {sorted(unknown)}")
        insts = [i for i in insts if i.symbol in wanted]
    today = dt.datetime.now(dt.UTC).date()
    frame = dukascopy_coverage_frame(raw_root(), "h1", insts, cfg.h1_start, today)
    windows = dukascopy_windows(frame)
    catalog = Catalog()

    state: dict[str, str] = {}
    ingest: list[Instrument] = []  # absent, pilot or grown
    derive: list[Instrument] = []  # incomplete: 1D / quality only
    for i in insts:
        w = windows.get(i.symbol)
        s = reference_state(catalog, i.symbol, w)
        if s == "ingested":
            state[i.symbol] = "ingested"
        elif s == "incomplete":
            derive.append(i)
        elif w is None or w.first is None:
            state[i.symbol] = "waiting: no window"
        else:
            ingest.append(i)

    if ingest:
        defects = _defects_module()
        spans = {i.symbol: (windows[i.symbol].first, windows[i.symbol].last) for i in ingest}
        rows = {r["symbol"]: r for r in defects.run(list(spans), spans).iter_rows(named=True)}
        short = [i for i in ingest if not (rows[i.symbol]["d008_1h"] and rows[i.symbol]["d008_1d"])]
        state |= {i.symbol: "waiting: window shorter than D-008" for i in short}
        ingest = [i for i in ingest if i not in short]
        found = {i.symbol: defects.present(rows[i.symbol]) for i in ingest}
        found = {s: f for s, f in found.items() if f}
        # D-672 (2): the D-717 stop is per instrument -- a flag holds that instrument only
        state |= {s: f"held (D-717): {', '.join(f)}" for s, f in found.items()}
        ingest = [i for i in ingest if i.symbol not in found]
        for s, ev in ((i.symbol, rows[i.symbol]["verified_events"]) for i in ingest):
            if ev:
                print(f"{s}: verified event(s) {ev} kept unchanged (D-672), not a stop")
        if found:
            print(f"HELD (D-717): {found} -- raise it; the others proceed")
        if ingest:
            print(f"D-717: no defect family in {', '.join(i.symbol for i in ingest)}")
    waiting = sum(v.startswith(("waiting", "held")) for v in state.values())
    print(
        f"D-661: {len(insts)} instrument(s) -- {sum(v == 'ingested' for v in state.values())} "
        f"ingested, {len(ingest)} to ingest, {len(derive)} to derive, {waiting} waiting or held"
    )

    failed: list[str] = []
    if not args.dry_run:
        pilots = [i for i in ingest if reference_state(catalog, i.symbol, None) == "pilot"]
        others = [i for i in ingest if i not in pilots]
        for group, flag in ((others, "--set-reference"), (pilots, "--rehash")):
            if group:
                cmd = ["data", "ingest", "dukascopy"]
                cmd += ["--instruments", ",".join(i.instrument_id for i in group), flag]
                for i in group:
                    cmd += ["--expect-window", f"{i.symbol}={_span(windows[i.symbol])}"]
                if sfac(*cmd) != 0:
                    failed.append(f"ingest {','.join(i.symbol for i in group)}")
        for inst in ingest + derive:
            s = inst.symbol
            if reference_state(Catalog(), s, windows.get(s)) not in ("incomplete", "ingested"):
                failed.append(f"{s}: no current 1H reference after the ingest")
                continue
            steps = [
                ("data", "resample", "--symbol", s, "--from", "1H", "--to", "1D"),
                ("data", "quality", "--symbol", s),
                ("costs", "show", s),
            ]
            steps[0] += ("--set-reference",)
            ok = all(sfac(*step) == 0 for step in steps)
            if ok and reference_state(Catalog(), s, windows.get(s)) == "ingested":
                state[s] = "ingested now"
            else:
                failed.append(f"{s}: resample / quality / costs")
    for i in ingest + derive:
        state.setdefault(i.symbol, "to do (dry run)" if args.dry_run else "failed")

    status = pl.DataFrame(
        [
            {
                "symbol": i.symbol,
                "state": state[i.symbol],
                "window_first": w.first if w else None,
                "window_last": w.last if w and w.first else None,
                "years": w.years if w else 0.0,
                "complete": w.complete if w else False,
                "bounding_gap": w.bounding_gap if w else None,
                "missing_before": w.missing_before if w else 0,
                "checked_on": today.isoformat(),
            }
            for i in insts
            for w in [windows.get(i.symbol)]
        ]
    )
    if not args.dry_run and not args.symbols:  # the status file always covers all 29
        status.write_csv(STATUS)
    print()
    for r in status.iter_rows(named=True):
        span = f"{r['window_first']}..{r['window_last']}" if r["window_first"] else "-"
        print(
            f"  {r['symbol']:<16}{r['state']:<36}{span:<18}{r['years']:>6} y  "
            f"gap {r['bounding_gap'] or '-'}"
        )
    if failed:
        print(f"FAILED: {failed}")
        return 2
    return 1 if any(v.startswith("held") for v in state.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
