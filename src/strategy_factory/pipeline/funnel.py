"""The funnel orchestrator (F-X.1, T15a §3; D-653, D-662, D-663).

``sfac funnel run <funnel-config>`` runs, per timeframe, ``s01_edge -> s02_screen -> s03_entry``,
each stage reading the previous stage's **real** run through ``stage_inputs``, and -- unless
``--no-control`` -- each stage's **control arm**: the same inputs on reshuffled bars (D-662, as
T13 and T14 ran it). Six stage runs per timeframe, in order: s01 real, s01 control, s02 real, s02
control, s03 real, s03 control.

* **Link** (D-663): a ``funnel_runs`` row and one ``funnel_stage_runs`` row per (timeframe,
  stage, arm), with the stage's registry run.
* **Resume**: every stage row carries its ``stage_key`` -- the content hash of the stage's
  resolved config (with the upstream run ids), its stage-config hash, the gate file, the synthetic
  generator (inside the config) and the code version. ``sfac funnel run`` on a config whose
  **funnel key** matches an unfinished funnel run resumes it: a stage whose row is ``done`` (or
  ``empty``) under the same key is skipped and its run feeds the next stage; the first unfinished
  one runs from scratch. A dirty working tree never resumes (D-352).
* **Empty**: a stage with no input (no pass upstream) runs nothing and is recorded ``empty``.
* **Synthetic** (D-654): a ``null`` / ``planted`` source is resolved once per funnel run -- the
  generator settings in full, the planted assignment over the whole scope -- and carried in every
  stage run's config.

The stage runs themselves are ordinary ``sfac run`` runs (``pipeline/stage_run.py``); the
orchestrator is written against a small :class:`StageRunner` so resume can be tested without the
store.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from strategy_factory.core.config import PipelineConfig, SourceRef, canonical_json, config_hash
from strategy_factory.pipeline.funnel_config import FunnelConfig
from strategy_factory.registry.funnel import FunnelRegistry, StageSlot
from strategy_factory.registry.writer import DIRTY_SUFFIX

log = logging.getLogger(__name__)

S01, S02, S03 = "s01_edge", "s02_screen", "s03_entry"
UPSTREAM = {S02: S01, S03: S02}
ARMS = ("real", "control")


class StageRunner(Protocol):
    """What the orchestrator needs from the stage machinery (the default: ``DefaultRunner``)."""

    def scope(self, cfg: FunnelConfig, timeframe: str) -> tuple[str, ...]:
        """The stage-1 symbols of ``timeframe`` (a broker scope expanded, D-616)."""
        ...

    def resolve(self, cfg: PipelineConfig) -> PipelineConfig:
        """``cfg`` with its snapshots and cost inputs pinned (no registry row)."""
        ...

    def run(self, cfg: PipelineConfig, on_start: Callable[[str], None]) -> str:
        """Run the one stage of a resolved ``cfg``; return its registry run id."""
        ...

    def passed(self, stage: str, run_id: str, timeframe: str, source_id: str) -> tuple[str, ...]:
        """Symbols that go on from a finished run: stage-1 passes or stage-2 selections."""
        ...


@dataclass(frozen=True)
class Hashes:
    """What besides the stage config decides a stage run's result (D-805, D-807)."""

    stage_config: dict[str, str]  # stage -> stage-config hash
    gates: str  # sha256 of the gate file
    code_version: str


@dataclass
class StageOutcome:
    slot: StageSlot
    status: str  # done, empty (skipped or run)
    run_id: str | None
    reused: bool
    inputs: int


@dataclass
class FunnelResult:
    funnel_id: str
    resumed: bool
    control: bool
    source: SourceRef | None
    stages: list[StageOutcome] = field(default_factory=list)
    seconds: float = 0.0

    def run_of(self, timeframe: str, stage: str, arm: str) -> str | None:
        for o in self.stages:
            if o.slot == (timeframe, stage, arm):
                return o.run_id
        return None


def _sha(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def funnel_key(cfg: FunnelConfig, control: bool, hashes: Hashes, generator: Any) -> str:
    """The content of a funnel run: its config, the control flag, everything that decides the
    stages' results, and the synthetic generator settings."""
    return _sha(
        {
            "funnel": cfg.canonical(),
            "control": control,
            "stage_config": hashes.stage_config,
            "gates": hashes.gates,
            "code_version": hashes.code_version,
            "generator": generator,
        }
    )


def stage_key(cfg: PipelineConfig, stage: str, hashes: Hashes) -> str:
    return _sha(
        {
            "config_hash": config_hash(cfg.canonical()),
            "stage": stage,
            "stage_config": hashes.stage_config[stage],
            "gates": hashes.gates,
            "code_version": hashes.code_version,
        }
    )


def empty_key(upstream_run: str | None, stage: str, arm: str, hashes: Hashes) -> str:
    return _sha({"empty": stage, "arm": arm, "upstream": upstream_run, **hashes.__dict__})


def stage_config(
    cfg: FunnelConfig,
    stage: str,
    timeframe: str,
    arm: str,
    source: SourceRef | None,
    upstream_run: str | None = None,
    symbols: tuple[str, ...] = (),
) -> PipelineConfig:
    """One stage run's config, as the hand-written ``configs/pipeline/s0*_*.yaml`` are."""
    common: dict[str, Any] = {
        "universe": cfg.universe,
        "gates": cfg.gates,
        "timeframes": (timeframe,),
        "stages": (stage,),
        "seed": cfg.seed,
        "control": "random_walk" if arm == "control" else "none",
        "source": source,
    }
    if stage == S01:
        if cfg.symbol_scope == "broker":
            return PipelineConfig(symbol_scope="broker", **common)
        return PipelineConfig(symbol_scope="listed", symbols=cfg.symbols, **common)
    assert upstream_run is not None
    return PipelineConfig(
        symbol_scope="stage_inputs",
        stage_inputs={UPSTREAM[stage]: upstream_run},
        symbols=symbols,
        **common,
    )


class Funnel:
    def __init__(
        self,
        cfg: FunnelConfig,
        registry: FunnelRegistry,
        runner: StageRunner,
        hashes: Hashes,
        source: SourceRef | None,
        notes: str = "",
    ) -> None:
        self.cfg = cfg
        self.registry = registry
        self.runner = runner
        self.hashes = hashes
        self.source = source
        self.notes = notes

    def run(self, *, control: bool = True, fresh: bool = False) -> FunnelResult:
        started = dt.datetime.now(dt.UTC)
        control = control and self.cfg.control
        generator = None if self.source is None else self.source.model_dump(mode="json")
        key = funnel_key(self.cfg, control, self.hashes, generator)
        dirty = self.hashes.code_version.endswith(DIRTY_SUFFIX)
        funnel_id = None if (fresh or dirty) else self.registry.resumable(key)
        resumed = funnel_id is not None
        if dirty and not fresh:
            log.warning("funnel: dirty working tree (%s): starting fresh, never resuming (D-352)",
                        self.hashes.code_version)  # fmt: skip
        if funnel_id is None:
            config = {"funnel": self.cfg.canonical(), "source": generator}
            funnel_id = self.registry.start_funnel(
                config=config,
                config_hash=_sha(config),
                funnel_key=key,
                code_version=self.hashes.code_version,
                seed=self.cfg.seed,
                source=self.cfg.source.kind,
                control=control,
                notes=self.notes or ("--no-control" if not control else ""),
            )
        else:
            self.registry.reopen(funnel_id)
        existing = self.registry.stages(funnel_id) if resumed else {}
        result = FunnelResult(
            funnel_id=str(funnel_id), resumed=resumed, control=control, source=self.source
        )
        arms = ARMS if control else ("real",)
        try:
            for tf in self.cfg.timeframes:
                real_run: str | None = None  # the upstream real run of the next stage
                for stage in self.cfg.stages:
                    symbols: tuple[str, ...] = ()
                    if stage != S01:
                        upstream = UPSTREAM[stage]
                        symbols = (
                            ()
                            if real_run is None
                            else self.runner.passed(
                                upstream, real_run, tf, self.source.id if self.source else "real"
                            )
                        )
                    next_real: str | None = None
                    for arm in arms:
                        outcome = self._stage(
                            funnel_id, existing, tf, stage, arm, real_run, symbols
                        )
                        result.stages.append(outcome)
                        if arm == "real":
                            next_real = outcome.run_id
                    real_run = next_real
        except BaseException:
            self.registry.finish_funnel(funnel_id, "failed")
            raise
        self.registry.finish_funnel(funnel_id, "done")
        result.seconds = (dt.datetime.now(dt.UTC) - started).total_seconds()
        return result

    def _stage(
        self,
        funnel_id: uuid.UUID,
        existing: dict[StageSlot, Any],
        tf: str,
        stage: str,
        arm: str,
        upstream_run: str | None,
        symbols: tuple[str, ...],
    ) -> StageOutcome:
        slot: StageSlot = (tf, stage, arm)
        if stage != S01 and not symbols:
            key = empty_key(upstream_run, stage, arm, self.hashes)
            prior = existing.get(slot)
            same = bool(prior and prior.status == "empty" and prior.stage_key == key)
            if not same:
                self.registry.start_stage(funnel_id, slot, key, 0)
                self.registry.finish_stage(funnel_id, slot, "empty")
            return StageOutcome(slot, "empty", None, same, 0)
        cfg = stage_config(self.cfg, stage, tf, arm, self.source, upstream_run, symbols)
        resolved = self.runner.resolve(cfg)
        key = stage_key(resolved, stage, self.hashes)
        prior = existing.get(slot)
        if prior and prior.status == "done" and prior.stage_key == key and prior.run_id:
            log.info("funnel: %s %s %s done under the same key: reused %s", tf, stage, arm,
                     prior.run_id)  # fmt: skip
            return StageOutcome(slot, "done", prior.run_id, True, len(resolved.symbols))
        self.registry.start_stage(funnel_id, slot, key, len(resolved.symbols))
        try:
            run_id = self.runner.run(
                resolved, lambda rid: self.registry.set_stage_run(funnel_id, slot, rid)
            )
        except BaseException:
            self.registry.finish_stage(funnel_id, slot, "failed")
            raise
        self.registry.finish_stage(funnel_id, slot, "done")
        return StageOutcome(slot, "done", run_id, False, len(resolved.symbols))


def write_funnel_summary(result: FunnelResult, folder: Path) -> Path:
    """``<artifacts>/funnels/<funnel_id>/funnel.json``: the stage runs of a funnel run."""
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        "funnel_id": result.funnel_id,
        "resumed": result.resumed,
        "control": result.control,
        "source": None if result.source is None else result.source.id,
        "seconds": result.seconds,
        "stages": [
            {
                "timeframe": o.slot[0],
                "stage": o.slot[1],
                "arm": o.slot[2],
                "status": o.status,
                "run_id": o.run_id,
                "reused": o.reused,
                "inputs": o.inputs,
            }
            for o in result.stages
        ],
    }
    path = folder / "funnel.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return path
