"""T04j: ingest every Dukascopy instrument over its D-661 window, and re-derive it when it grows.

The single resume command while the download runs (D-657, D-661). Local only, no network (D-031);
run from the stream B worktree, as often as the download progresses::

    uv run python scripts/pilots/T04j_resume.py              # measure, ingest, derive, report
    uv run python scripts/pilots/T04j_resume.py --dry-run    # windows, status and D-717 only
    uv run python scripts/pilots/T04j_resume.py --symbols EURUSD,USDCHF   # only these

Only **settled** raw months are read (``rawfiles.is_settled``: the data file and its manifest
written, no ``.partial``), so a month the download is still writing is never read. Per instrument,
in the task file's order (``docs/tasks/T04j_dukascopy_ingest.md``):

1. **The window (D-661):** the longest contiguous complete run of months ending at the last complete
   month. No window: it waits.
2. **Status:** *done* when the 1H reference is Dukascopy hash version 2 **over exactly the current
   window** (its first and last bar's months), the 1D reference is ``derived_from`` it (D-032) and
   both have a quality status. Done instruments are skipped, so a re-run writes nothing. A window
   that grew (a gap closed, or a new month) is **not** done: it is re-ingested as a new versioned
   snapshot and the references move; nothing is overwritten.
3. **D-008:** measured on the window's bars; a window too short to split waits (D-661).
4. **D-717:** the defect families are re-measured over the window of every instrument about to be
   ingested (``scripts/analysis/T04j_defects.py``). **An instrument with any family present is held
   and nothing is written for it** (per instrument, D-672); the others proceed. A bar listed in
   ``verified_events`` (D-672) is reported and is not a stop.
5. **Ingest 1H** (``sfac data ingest dukascopy``, which applies the window itself) with
   ``--set-reference``; a hash-version-1 pilot reference (EURUSD, XAUUSD, USA500IDXUSD) with
   ``--rehash`` (event note ``rehash v1→v2``).
6. **Build 1D** (D-010, D-032): ``sfac data resample --from 1H --to 1D --set-reference``, once.
7. **Quality** for both snapshots, then ``sfac costs show`` (the 1H development segment, D-523).

Writes ``docs/reviews/T04j_instrument_status.csv`` (per instrument: state, window, the gap that
bounds it) and prints the same summary. Exit 0 when every step ran; 1 when an instrument was held
by D-717 (raise it); 2 when a step failed.
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
from strategy_factory.core.errors import SfacError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import load_dukascopy_config
from strategy_factory.data.coverage import Window, dukascopy_coverage_frame, dukascopy_windows
from strategy_factory.data.download.dukascopy import Instrument, load_instruments
from strategy_factory.data.download.rawfiles import raw_root

REPO = Path(__file__).resolve().parents[2]
STATUS = REPO / "docs" / "reviews" / "T04j_instrument_status.csv"
DEFECTS = REPO / "scripts" / "analysis" / "T04j_defects.py"


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


def _reference(catalog: Catalog, symbol: str, timeframe: str) -> Any:
    try:
        return catalog.get_reference(symbol, timeframe)
    except SfacError:
        return None


def _month(ts: Any) -> str | None:
    return None if ts is None else ts.strftime("%Y-%m")


def over_window(catalog: Catalog, symbol: str, w: Window) -> bool:
    """The 1H reference is Dukascopy v2 and spans exactly the window's months."""
    h1 = _reference(catalog, symbol, "1H")
    return (
        h1 is not None
        and h1.source == "dukascopy"
        and h1.hash_version == 2
        and (_month(h1.first_ts), _month(h1.last_ts)) == (w.first, w.last)
    )


def is_done(catalog: Catalog, symbol: str, w: Window) -> bool:
    """Over the current window, the 1D reference derived from it, a quality status on both."""
    if not over_window(catalog, symbol, w):
        return False
    h1, d1 = _reference(catalog, symbol, "1H"), _reference(catalog, symbol, "1D")
    if d1 is None or d1.derived_from is None or d1.derived_from.snapshot_hash != h1.snapshot_hash:
        return False
    return all(catalog.quality_status(m.key()) != "unchecked" for m in (h1, d1))


def is_pilot(catalog: Catalog, symbol: str) -> bool:
    """The reference is still a T04e hash-version-1 pilot: re-hash it (T04e §1)."""
    h1 = _reference(catalog, symbol, "1H")
    return h1 is not None and h1.source == "dukascopy" and h1.hash_version == 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="Windows, status and D-717 only.")
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
    state = {i.symbol: "waiting: no window" for i in insts if windows[i.symbol].first is None}
    candidates = [i for i in insts if windows[i.symbol].first is not None]
    done = [i for i in candidates if is_done(catalog, i.symbol, windows[i.symbol])]
    state |= {i.symbol: "ingested" for i in done}
    todo = [i for i in candidates if i not in done]

    if todo:
        defects = _defects_module()
        spans = {i.symbol: (windows[i.symbol].first, windows[i.symbol].last) for i in todo}
        rows = {r["symbol"]: r for r in defects.run(list(spans), spans).iter_rows(named=True)}
        short = [i for i in todo if not (rows[i.symbol]["d008_1h"] and rows[i.symbol]["d008_1d"])]
        state |= {i.symbol: "waiting: window shorter than D-008" for i in short}
        todo = [i for i in todo if i not in short]
        found = {i.symbol: defects.present(rows[i.symbol]) for i in todo}
        found = {s: f for s, f in found.items() if f}
        # D-672 (2): the D-717 stop is per instrument -- a flag holds that instrument only
        state |= {s: f"held (D-717): {', '.join(f)}" for s, f in found.items()}
        todo = [i for i in todo if i.symbol not in found]
        for s, ev in ((i.symbol, rows[i.symbol]["verified_events"]) for i in todo):
            if ev:
                print(f"{s}: verified event(s) {ev} kept unchanged (D-672), not a stop")
        if found:
            print(f"HELD (D-717): {found} -- raise it; the others proceed")
        if todo:
            print(f"D-717: no defect family in {', '.join(i.symbol for i in todo)}")
    print(
        f"windows (D-661): {len(candidates)} of {len(insts)} -- {len(done)} already ingested, "
        f"{len(todo)} to ingest; {len(insts) - len(done) - len(todo)} waiting"
    )

    failed: list[str] = []
    if todo and not args.dry_run:
        pilots = [i for i in todo if is_pilot(catalog, i.symbol)]
        others = [i for i in todo if i not in pilots]
        for group, flag in ((others, "--set-reference"), (pilots, "--rehash")):
            if group:
                ids = ",".join(i.instrument_id for i in group)
                if sfac("data", "ingest", "dukascopy", "--instruments", ids, flag) != 0:
                    failed.append(f"ingest {ids}")
        for inst in todo:
            s = inst.symbol
            if not over_window(Catalog(), s, windows[s]):
                failed.append(f"{s}: the 1H reference does not span the window after the ingest")
                continue
            steps = [
                (
                    "data",
                    "resample",
                    "--symbol",
                    s,
                    "--from",
                    "1H",
                    "--to",
                    "1D",
                    "--set-reference",
                ),
                ("data", "quality", "--symbol", s),
                ("costs", "show", s),
            ]
            if all(sfac(*step) == 0 for step in steps) and is_done(Catalog(), s, windows[s]):
                state[s] = "ingested now"
            else:
                failed.append(f"{s}: resample / quality / costs")
    for i in todo:
        state.setdefault(i.symbol, "to ingest (dry run)" if args.dry_run else "failed")

    status = pl.DataFrame(
        [
            {
                "symbol": i.symbol,
                "state": state[i.symbol],
                "window_first": windows[i.symbol].first,
                "window_last": windows[i.symbol].last if windows[i.symbol].first else None,
                "years": windows[i.symbol].years,
                "complete": windows[i.symbol].complete,
                "bounding_gap": windows[i.symbol].bounding_gap,
                "missing_before": windows[i.symbol].missing_before,
                "checked_on": today.isoformat(),
            }
            for i in insts
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
