"""Read a funnel run's artifacts into one plain context (D-655: never recomputed).

Every number the report shows comes from here, and here only from the artifacts -- each stage run's
``index.csv`` and ``summary.json`` files, the funnel's ``funnel.json`` and ``truth.json`` -- and the
funnel's registry row. Counts are counts of artifact rows; nothing is re-derived from bars.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

S01, S02, S03 = "s01_edge", "s02_screen", "s03_entry"
STAGES = (S01, S02, S03)
#: the column of each stage's index that says a row goes on
PASS_COLUMN = {S01: "passed", S02: "selected", S03: "gate_passed"}


def read_index(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class StageRun:
    timeframe: str
    stage: str
    arm: str
    status: str
    run_id: str | None
    rows: list[dict[str, str]] = field(default_factory=list)

    @property
    def folder_name(self) -> str:
        return self.stage

    def entered(self) -> list[dict[str, str]]:
        """The rows that were evaluated (stage 1: profiled, not skipped)."""
        if self.stage == S01:
            return [r for r in self.rows if r.get("status") == "profiled"]
        return self.rows

    def passing(self) -> list[dict[str, str]]:
        return [r for r in self.entered() if r.get(PASS_COLUMN[self.stage]) == "True"]

    def counts(self) -> dict[str, int]:
        entered, passing = self.entered(), self.passing()
        return {
            "entered": len(entered),
            "passed": len(passing),
            "symbols_entered": len({r["symbol"] for r in entered}),
            "symbols_passed": len({r["symbol"] for r in passing}),
        }


@dataclass
class Candidate:
    """A candidate that entered stage 3, with its lineage (T15a §5)."""

    timeframe: str
    stage3: dict[str, Any]
    stage2: dict[str, Any] | None
    stage1: dict[str, Any] | None

    @property
    def passed(self) -> bool:
        return bool(self.stage3["gate_passed"])

    @property
    def key(self) -> str:
        i = self.stage3["identity"]
        return f"{i['timeframe']}-{i['symbol']}-{i['direction']}-{i['method']}"


@dataclass
class FunnelContext:
    funnel_id: str
    row: dict[str, Any]
    summary: dict[str, Any]
    runs: list[StageRun]
    candidates: list[Candidate]
    truth: dict[str, Any] | None
    artifacts: Path

    @property
    def timeframes(self) -> list[str]:
        return list(dict.fromkeys(r.timeframe for r in self.runs))

    @property
    def source_kind(self) -> str:
        return str(self.row["source"])

    @property
    def control(self) -> bool:
        return bool(self.row["control"])

    def run(self, timeframe: str, stage: str, arm: str) -> StageRun | None:
        for r in self.runs:
            if (r.timeframe, r.stage, r.arm) == (timeframe, stage, arm):
                return r
        return None

    def summaries(self, run: StageRun) -> list[dict[str, Any]]:
        if run.run_id is None:
            return []
        folder = self.artifacts / run.run_id / run.stage
        return [
            read_json(folder / r["candidate_id"] / "summary.json")
            for r in run.entered()
            if (folder / r["candidate_id"] / "summary.json").is_file()
        ]


def failing_criteria(ctx: FunnelContext, run: StageRun) -> list[tuple[str, int]]:
    """How often each gate criterion failed, by frequency (stage 1 from its profiles' gates)."""
    counts: Counter[str] = Counter()
    if run.stage == S01:
        for s in ctx.summaries(run):
            counts.update(g["metric"] for g in s["profile"]["gate"] if not g["passed"])
    else:
        for r in run.entered():
            counts.update(c for c in (r.get("failed_criteria") or "").split(";") if c)
    return counts.most_common()


def quality_split(run: StageRun) -> list[dict[str, Any]]:
    """Stage 1's pass rate by data-quality status (T12 §4)."""
    out = []
    for status in sorted({r.get("quality_status", "") for r in run.entered()}):
        rows = [r for r in run.entered() if r.get("quality_status", "") == status]
        passed = sum(1 for r in rows if r.get("passed") == "True")
        out.append({"status": status, "profiles": len(rows), "passed": passed})
    return out


def truth_errors(ctx: FunnelContext) -> dict[str, int]:
    """Per timeframe, the symbols the truth could not be built for (no series, e.g. too short
    for a split): they are left out of every power denominator, and the report says how many."""
    if ctx.truth is None:
        return {}
    return {
        tf: sum(1 for t in per.values() if "error" in t)
        for tf, per in ctx.truth["timeframes"].items()
    }


def planted_truth(ctx: FunnelContext) -> list[dict[str, Any]]:
    """Planted runs: per timeframe and cell, the symbols and how many of them have their planted
    profile at each stage (a TF plant is two-sided: long or short counts)."""
    if ctx.truth is None or ctx.source_kind != "planted":
        return []
    out = []
    for tf, per in ctx.truth["timeframes"].items():
        by_cell: dict[str, list[str]] = {}
        for sym, t in per.items():
            if "cell" in t:
                by_cell.setdefault(t["cell"], []).append(sym)
        for cell, symbols in sorted(by_cell.items()):
            kind, direction = cell.split("|")[:2] if cell != "null" else ("", "")
            rec: dict[str, Any] = {"timeframe": tf, "cell": cell, "symbols": len(symbols)}
            for stage in STAGES:
                run = ctx.run(tf, stage, "real")
                hits = set()
                if run is not None:
                    for r in run.passing():
                        if r["symbol"] in symbols and (
                            cell == "null"
                            or (r["edge_type"] == kind and direction in ("both", r["direction"]))
                        ):
                            hits.add(r["symbol"])
                rec[stage] = len(hits)
            out.append(rec)
    return out


def read_funnel(funnel_id: str, artifacts: Path, row: dict[str, Any]) -> FunnelContext:
    folder = artifacts / "funnels" / funnel_id
    summary = read_json(folder / "funnel.json")
    truth_path = folder / "truth.json"
    truth = read_json(truth_path) if truth_path.is_file() else None
    runs = []
    for s in summary["stages"]:
        rows: list[dict[str, str]] = []
        if s["run_id"]:
            rows = read_index(artifacts / s["run_id"] / s["stage"] / "index.csv")
        runs.append(StageRun(s["timeframe"], s["stage"], s["arm"], s["status"], s["run_id"], rows))
    ctx = FunnelContext(funnel_id, row, summary, runs, [], truth, artifacts)
    for tf in ctx.timeframes:
        r3 = ctx.run(tf, S03, "real")
        r2 = ctx.run(tf, S02, "real")
        r1 = ctx.run(tf, S01, "real")
        if r3 is None or r3.run_id is None:
            continue
        for s3 in ctx.summaries(r3):
            s2 = _parent(artifacts, r2, s3["identity"]["parent_id"])
            s1 = _parent(artifacts, r1, s2["identity"]["parent_id"]) if s2 else None
            ctx.candidates.append(Candidate(tf, s3, s2, s1))
    ctx.candidates.sort(key=lambda c: (not c.passed, c.timeframe, c.key))
    return ctx


def _parent(artifacts: Path, run: StageRun | None, parent_id: str) -> dict[str, Any] | None:
    if run is None or run.run_id is None:
        return None
    path = artifacts / run.run_id / run.stage / parent_id / "summary.json"
    return read_json(path) if path.is_file() else None
