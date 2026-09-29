"""T04j: ingest every Dukascopy instrument whose h1 raw set is complete and not yet ingested.

The single resume command for the instruments that wait on the download (D-657). Local only, no
network (D-031); run from the stream B worktree after the user's download script::

    uv run python scripts/pilots/T04j_resume.py              # measure, ingest, derive, report
    uv run python scripts/pilots/T04j_resume.py --dry-run    # coverage, status and D-717 only

Per instrument, in the task file's order (``docs/tasks/T04j_dukascopy_ingest.md``, scope 1-6):

1. **Coverage (D-386 copied, per instrument since D-657):** an instrument with a required month
   missing on either side **waits**; nothing is written for it.
2. **Status:** a complete instrument is *done* when its 1H reference is Dukascopy hash version 2,
   its 1D reference is ``derived_from`` that 1H reference (D-032), and both have a quality status.
   Done instruments are skipped, so a re-run writes nothing.
3. **D-717:** ``scripts/analysis/T04j_defects.py`` re-measures the defect families on the complete
   raw set of every instrument about to be ingested. **Any family present stops the run before
   anything is written** (exit 1).
4. **Ingest 1H** with ``--set-reference``; an instrument whose reference is still the hash-version-1
   pilot (EURUSD, XAUUSD, USA500IDXUSD) with ``--rehash`` (event note ``rehash v1→v2``).
5. **Build 1D** (D-010, D-032): ``sfac data resample --from 1H --to 1D --set-reference``, once.
6. **Quality** for both snapshots, then ``sfac costs show`` (the 1H development segment, D-523).

Writes ``docs/reviews/T04j_instrument_status.csv`` (per instrument: state, missing months) and
prints the same summary. Exit 0 when every step ran; 1 on a D-717 stop; 2 when a step failed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import subprocess
import sys
from pathlib import Path

import polars as pl

from strategy_factory.cli import utf8_output
from strategy_factory.core.errors import SfacError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import load_dukascopy_config
from strategy_factory.data.coverage import dukascopy_coverage_frame, dukascopy_gaps
from strategy_factory.data.download.dukascopy import Instrument, load_instruments
from strategy_factory.data.download.rawfiles import raw_root

REPO = Path(__file__).resolve().parents[2]
STATUS = REPO / "docs" / "reviews" / "T04j_instrument_status.csv"
DEFECTS = REPO / "scripts" / "analysis" / "T04j_defects.py"


def _defects_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("T04j_defects", DEFECTS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sfac(*args: str) -> int:
    """One ``sfac`` command in a child process (its output goes straight to this console)."""
    print(f"\n$ sfac {' '.join(args)}", flush=True)
    return subprocess.run(
        [sys.executable, "-m", "strategy_factory.cli", *args], check=False
    ).returncode


def _reference(catalog: Catalog, symbol: str, timeframe: str):  # type: ignore[no-untyped-def]
    try:
        return catalog.get_reference(symbol, timeframe)
    except SfacError:
        return None


def is_done(catalog: Catalog, symbol: str) -> bool:
    """1H reference = Dukascopy v2, 1D reference derived from it, a quality status on both."""
    h1, d1 = _reference(catalog, symbol, "1H"), _reference(catalog, symbol, "1D")
    if h1 is None or d1 is None or h1.source != "dukascopy" or h1.hash_version != 2:
        return False
    if d1.derived_from is None or d1.derived_from.snapshot_hash != h1.snapshot_hash:
        return False
    return all(catalog.quality_status(m.key()) != "unchecked" for m in (h1, d1))


def is_pilot(catalog: Catalog, symbol: str) -> bool:
    """The reference is still a T04e hash-version-1 pilot: re-hash it (T04e §1)."""
    h1 = _reference(catalog, symbol, "1H")
    return h1 is not None and h1.source == "dukascopy" and h1.hash_version == 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="Coverage, status and D-717 only.")
    args = parser.parse_args(argv)
    utf8_output()

    cfg = load_dukascopy_config()
    insts: list[Instrument] = load_instruments(cfg.universe_file)
    today = dt.datetime.now(dt.UTC).date()
    gaps = dukascopy_gaps(dukascopy_coverage_frame(raw_root(), "h1", insts, cfg.h1_start, today))
    catalog = Catalog()
    complete = [i for i in insts if i.symbol not in gaps]
    done = [i for i in complete if is_done(catalog, i.symbol)]
    todo = [i for i in complete if i not in done]
    print(
        f"coverage (D-657): {len(complete)} of {len(insts)} complete -- "
        f"{len(done)} already ingested, {len(todo)} to ingest; {len(gaps)} waiting"
    )

    ingested: list[str] = []
    failed: list[str] = []
    if todo:
        defects = _defects_module()
        rows = defects.run([i.symbol for i in todo])
        found = {r["symbol"]: defects.present(r) for r in rows.iter_rows(named=True)}
        found = {s: f for s, f in found.items() if f}
        if found:
            print(f"STOP (D-717): defect families present; nothing ingested: {found}")
            return 1
        print(f"D-717: no defect family in {', '.join(i.symbol for i in todo)}")

    if todo and not args.dry_run:
        pilots = [i for i in todo if is_pilot(catalog, i.symbol)]
        others = [i for i in todo if i not in pilots]
        for group, flag in ((others, "--set-reference"), (pilots, "--rehash")):
            if group:
                ids = ",".join(i.instrument_id for i in group)
                if sfac("data", "ingest", "dukascopy", "--instruments", ids, flag) != 0:
                    failed.append(f"ingest {ids}")
        catalog = Catalog()
        for inst in todo:
            s = inst.symbol
            h1 = _reference(catalog, s, "1H")
            if h1 is None or h1.source != "dukascopy" or h1.hash_version != 2:
                failed.append(f"{s}: no v2 1H reference after the ingest")
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
            if all(sfac(*step) == 0 for step in steps) and is_done(Catalog(), s):
                ingested.append(s)
            else:
                failed.append(f"{s}: resample / quality / costs")

    status = pl.DataFrame(
        [
            {
                "symbol": i.symbol,
                "state": (
                    "waiting"
                    if i.symbol in gaps
                    else "ingested"
                    if i in done or i.symbol in ingested
                    else "complete, not ingested"
                ),
                "missing_months": len(gaps.get(i.symbol, [])),
                "first_missing": gaps[i.symbol][0] if i.symbol in gaps else None,
                "last_missing": gaps[i.symbol][-1] if i.symbol in gaps else None,
                "checked_on": today.isoformat(),
            }
            for i in insts
        ]
    )
    if not args.dry_run:
        status.write_csv(STATUS)
    print(
        "\n"
        + "\n".join(
            f"  {r[0]:<16}{r[1]:<24}{r[2]:>5}  {r[3] or ''}..{r[4] or ''}" for r in status.rows()
        )
    )
    print(
        f"\ningested now: {', '.join(ingested) or 'none'}; already ingested: "
        f"{', '.join(i.symbol for i in done) or 'none'}; waiting: {len(gaps)}"
    )
    if failed:
        print(f"FAILED: {failed}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
