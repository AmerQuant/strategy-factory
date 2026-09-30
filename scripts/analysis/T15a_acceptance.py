"""T15a acceptance (T15a §6): the numbers of the review, read from the funnels' artifacts.

* ``real FUNNEL_ID``: the real funnel against the merged T12-T14 runs -- per timeframe and stage,
  the passing keys (stage 1: symbol, edge type, direction; stage 2: + method; stage 3: + method)
  of the funnel and of the old run, what is common, new and missing; and the control arms' passes.
* ``null FUNNEL_ID [...]``: per funnel and timeframe, stage-by-stage counts and the share of
  symbols reaching the end of stage 3 (D-656), and the passing candidates.
* ``planted FUNNEL_ID``: power per cell and stage, the other profiles passing, the control arms.

Everything comes from ``index.csv`` files and the funnel's ``funnel.json`` / ``truth.json``.

    uv run python scripts/analysis/T15a_acceptance.py real <id> --csv docs/reviews/T15a_real.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from strategy_factory.pipeline.stage_run import artifacts_root

STAGES = ("s01_edge", "s02_screen", "s03_entry")
PASS = {"s01_edge": "passed", "s02_screen": "selected", "s03_entry": "gate_passed"}
#: the merged runs (T12 review §1, T13 review §2, T14 review §2)
OLD = {
    ("1D", "s01_edge", "real"): "db666562", ("1D", "s01_edge", "control"): "279018ed",
    ("1H", "s01_edge", "real"): "6f603a07", ("1H", "s01_edge", "control"): "9c4fcde5",
    ("1D", "s02_screen", "real"): "dea1d423", ("1D", "s02_screen", "control"): "dd27baf5",
    ("1H", "s02_screen", "real"): "6025ef15", ("1H", "s02_screen", "control"): "ae578471",
    ("1D", "s03_entry", "real"): "f72b80ee", ("1D", "s03_entry", "control"): "0a4fb887",
    ("1H", "s03_entry", "real"): "ce348ae8", ("1H", "s03_entry", "control"): "9d37799d",
}  # fmt: skip


def rows(root: Path, run: str | None, stage: str) -> list[dict[str, str]]:
    if not run:
        return []
    hits = [p for p in root.iterdir() if p.name.startswith(run)]
    if len(hits) != 1:
        return []
    path = hits[0] / stage / "index.csv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        out = list(csv.DictReader(fh))
    return [r for r in out if stage != "s01_edge" or r.get("status") == "profiled"]


def key(r: dict[str, str], stage: str) -> str:
    base = f"{r['symbol']} {r['edge_type']} {r['direction']}"
    return base if stage == "s01_edge" else f"{base} {r['method']}"


def passing(rs: list[dict[str, str]], stage: str) -> set[str]:
    return {key(r, stage) for r in rs if r.get(PASS[stage]) == "True"}


def funnel(root: Path, fid: str) -> tuple[dict[tuple[str, str, str], str | None], dict[str, Any]]:
    folder = root / "funnels" / fid
    summary = json.loads((folder / "funnel.json").read_text(encoding="utf-8"))
    runs = {(s["timeframe"], s["stage"], s["arm"]): s["run_id"] for s in summary["stages"]}
    return runs, summary


def real(root: Path, fid: str) -> list[dict[str, Any]]:
    runs, _ = funnel(root, fid)
    out = []
    for (tf, stage, arm), run in sorted(runs.items()):
        new = rows(root, run, stage)
        old = rows(root, OLD.get((tf, stage, arm)), stage)
        pn, po = passing(new, stage), passing(old, stage)
        out.append({
            "timeframe": tf, "stage": stage, "arm": arm, "entered_new": len(new),
            "entered_old": len(old), "passed_new": len(pn), "passed_old": len(po),
            "common": len(pn & po), "only_new": "; ".join(sorted(pn - po)),
            "only_old": "; ".join(sorted(po - pn)),
        })  # fmt: skip
    return out


def null(root: Path, fids: list[str]) -> list[dict[str, Any]]:
    out = []
    for fid in fids:
        runs, summary = funnel(root, fid)
        for tf in sorted({k[0] for k in runs}):
            rec: dict[str, Any] = {"funnel": fid, "source": summary.get("source"), "timeframe": tf}
            for stage in STAGES:
                for arm in ("real", "control"):
                    rs = rows(root, runs.get((tf, stage, arm)), stage)
                    p = [r for r in rs if r.get(PASS[stage]) == "True"]
                    rec[f"{stage}_{arm}_entered"] = len(rs)
                    rec[f"{stage}_{arm}_passed"] = len(p)
                    rec[f"{stage}_{arm}_symbols"] = len({r["symbol"] for r in p})
            scope = len(
                {r["symbol"] for r in rows(root, runs.get((tf, "s01_edge", "real")), "s01_edge")}
            )
            ended = rec["s03_entry_real_symbols"]
            rec["scope"] = scope
            rec["end_of_stage3_share"] = ended / scope if scope else None
            s3 = rows(root, runs.get((tf, "s03_entry", "real")), "s03_entry")
            rec["stage3_passes"] = "; ".join(sorted(passing(s3, "s03_entry")))
            out.append(rec)
    return out


def planted(root: Path, fid: str) -> list[dict[str, Any]]:
    runs, _ = funnel(root, fid)
    truth = json.loads((root / "funnels" / fid / "truth.json").read_text(encoding="utf-8"))
    out = []
    for tf, per in truth["timeframes"].items():
        cells: dict[str, list[str]] = {}
        for sym, t in per.items():
            if "cell" in t:
                cells.setdefault(t["cell"], []).append(sym)
        for cell, symbols in sorted(cells.items()):
            kind, direction = cell.split("|")[:2] if cell != "null" else ("", "")
            rec: dict[str, Any] = {"timeframe": tf, "cell": cell, "symbols": len(symbols)}
            for stage in STAGES:
                for arm in ("real", "control"):
                    rs = rows(root, runs.get((tf, stage, arm)), stage)
                    mine = set()
                    other = 0
                    for r in rs:
                        if r["symbol"] not in symbols or r.get(PASS[stage]) != "True":
                            continue
                        if (
                            cell != "null"
                            and r["edge_type"] == kind
                            and direction in ("both", r["direction"])
                        ):
                            mine.add(r["symbol"])
                        else:
                            other += 1
                    rec[f"{stage}_{arm}_planted"] = len(mine)
                    rec[f"{stage}_{arm}_other"] = other
            out.append(rec)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["real", "null", "planted"])
    ap.add_argument("funnel", nargs="+")
    ap.add_argument("--csv", type=Path)
    args = ap.parse_args()
    root = artifacts_root()
    if args.kind == "real":
        table = real(root, args.funnel[0])
    elif args.kind == "null":
        table = null(root, args.funnel)
    else:
        table = planted(root, args.funnel[0])
    if args.csv:
        with args.csv.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(table[0]))
            w.writeheader()
            w.writerows(table)
    for r in table:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
