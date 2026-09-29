"""``sfac funnel reproduce`` (F-0.7.4, F-X.2; D-663): rebuild a funnel run and prove it identical.

The funnel row stores its config and its synthetic source in full, and every stage row its
registry run. Reproduction **refuses** a dirty or different code version (the same code is part of
what "the same result" means, D-352), re-runs the whole chain into a **new** funnel run with the
stored config, source and control flag, and compares every artifact file of every stage run with
the original's, byte for byte, after one normalisation: the values that name a run -- its run id,
its upstream run id, and the run config's hash (which contains the upstream run id) -- are replaced
on both sides by the same placeholder for the same (timeframe, stage, arm). Candidate ids carry no
run id (D-805), so they must match as they are.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from strategy_factory.core.config import SourceRef
from strategy_factory.core.errors import ConfigError
from strategy_factory.pipeline.funnel import Funnel, FunnelResult, Hashes, StageRunner
from strategy_factory.pipeline.funnel_config import FunnelConfig
from strategy_factory.registry.funnel import FunnelRegistry
from strategy_factory.registry.writer import DIRTY_SUFFIX


@dataclass
class ReproduceReport:
    original: str
    reproduction: str
    compared_files: int = 0
    differences: list[str] = field(default_factory=list)

    @property
    def identical(self) -> bool:
        return not self.differences


def normalise(data: bytes, mapping: dict[str, str]) -> bytes:
    for old in sorted(mapping, key=len, reverse=True):
        data = data.replace(old.encode("utf-8"), mapping[old].encode("utf-8"))
    return data


def _files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    return {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}


def compare_dirs(
    a: Path, b: Path, map_a: dict[str, str], map_b: dict[str, str]
) -> tuple[int, list[str]]:
    """Files of ``a`` and ``b`` (recursively), normalised; the relative paths that differ."""
    files_a, files_b = _files(a), _files(b)
    diffs = [f"only in the original: {k}" for k in sorted(files_a.keys() - files_b.keys())]
    diffs += [f"only in the reproduction: {k}" for k in sorted(files_b.keys() - files_a.keys())]
    for rel in sorted(files_a.keys() & files_b.keys()):
        left = normalise(files_a[rel].read_bytes(), map_a)
        if left != normalise(files_b[rel].read_bytes(), map_b):
            diffs.append(f"differs: {rel}")
    return len(files_a.keys() | files_b.keys()), diffs


def reproduce_funnel(
    funnel_id: str,
    *,
    registry: FunnelRegistry,
    runner: StageRunner,
    hashes: Hashes,
    artifacts: Path,
    run_config_hash: Callable[[str], str],
) -> tuple[ReproduceReport, FunnelResult]:
    fid = uuid.UUID(funnel_id)
    row: dict[str, Any] = registry.funnel(fid)
    recorded = str(row["code_version"])
    if recorded.endswith(DIRTY_SUFFIX) or recorded == "unknown":
        raise ConfigError(f"funnel {funnel_id} ran on {recorded!r}: not reproducible (D-352)")
    if recorded != hashes.code_version:
        raise ConfigError(
            f"funnel {funnel_id} ran on {recorded}, the checkout is {hashes.code_version}: "
            "check out the recorded commit to reproduce it"
        )
    cfg = FunnelConfig.model_validate(row["config"]["funnel"])
    stored = row["config"].get("source")
    source = None if stored is None else SourceRef.model_validate(stored)
    original = registry.stages(fid)
    new = Funnel(cfg, registry, runner, hashes, source, notes=f"reproduction of {funnel_id}").run(
        control=bool(row["control"]), fresh=True
    )
    report = ReproduceReport(original=funnel_id, reproduction=new.funnel_id)
    for o in new.stages:
        tf, stage, arm = o.slot
        before = original.get(o.slot)
        if before is None or before.status != o.status:
            report.differences.append(f"{o.slot}: status {before and before.status} -> {o.status}")
            continue
        if o.status != "done":
            continue
        assert before.run_id is not None and o.run_id is not None
        token = f"<{tf}|{stage}|{arm}>"
        map_a = {before.run_id: f"run{token}", run_config_hash(before.run_id): f"cfg{token}"}
        map_b = {o.run_id: f"run{token}", run_config_hash(o.run_id): f"cfg{token}"}
        upstream = [p for p in new.stages if p.slot[0] == tf and p.slot[2] == "real"]
        for p in upstream:  # the upstream real runs appear in stage_inputs / parent_run_id
            q = original.get(p.slot)
            if q and q.run_id and p.run_id:
                t = f"<{p.slot[0]}|{p.slot[1]}|real>"
                map_a[q.run_id] = f"run{t}"
                map_b[p.run_id] = f"run{t}"
        n, diffs = compare_dirs(
            artifacts / before.run_id / stage, artifacts / o.run_id / stage, map_a, map_b
        )
        report.compared_files += n
        report.differences += [f"{o.slot}: {d}" for d in diffs]
    return report, new
