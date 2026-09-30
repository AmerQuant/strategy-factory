"""``sfac funnel run``: the orchestrator wired to the real stages, store and registry (T15a).

:class:`DefaultRunner` runs each stage through ``pipeline/stage_run.py`` (an ordinary registry run
per stage); :func:`build_source` resolves a synthetic source once per funnel run (D-654, D-670);
:func:`funnel_hashes` collects what decides the stages' results besides their configs (the stage
configs, the gate file, the code version -- D-805, D-807). A synthetic funnel writes its truth --
the planted cell and positions of every series -- next to its summary.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from strategy_factory.core.config import (
    PipelineConfig,
    SourceRef,
    expand_broker_scope,
    resolve_config,
)
from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import load_split_config
from strategy_factory.data.split import RegistryLedger, SplitManager
from strategy_factory.data.store import SnapshotStore
from strategy_factory.pipeline.executor import load_executor_config, make_executor
from strategy_factory.pipeline.funnel import (
    S01,
    S02,
    Funnel,
    FunnelResult,
    Hashes,
    write_funnel_summary,
)
from strategy_factory.pipeline.funnel_config import FunnelConfig, load_funnel_config
from strategy_factory.pipeline.stage_run import artifacts_root, run_pipeline_config
from strategy_factory.registry.engine import make_engine
from strategy_factory.registry.funnel import FunnelRegistry
from strategy_factory.registry.writer import code_version

FUNNELS_DIR = "funnels"


def funnel_folder(root: Path, funnel_id: str) -> Path:
    """``<artifacts>/funnels/<funnel_id>/``: the funnel's summary, truth and report."""
    return root / FUNNELS_DIR / funnel_id


class DefaultRunner:
    def __init__(self, executor: Any = None) -> None:
        self.store = SnapshotStore()
        self.catalog = Catalog(self.store.root)
        self.root = artifacts_root()
        self.executor = executor

    def scope(self, cfg: FunnelConfig, timeframe: str) -> tuple[str, ...]:
        if cfg.symbol_scope == "listed":
            return cfg.symbols
        probe = PipelineConfig(
            symbol_scope="broker",
            universe=cfg.universe,
            timeframes=(timeframe,),
            stages=(S01,),
        )
        return expand_broker_scope(probe, self.catalog).symbols

    def resolve(self, cfg: PipelineConfig) -> PipelineConfig:
        return resolve_config(cfg, catalog_root=self.store.root)

    def run(self, cfg: PipelineConfig, on_start: Callable[[str], None]) -> str:
        return run_pipeline_config(cfg, executor=self.executor, on_start=on_start).run_id

    def passed(self, stage: str, run_id: str, timeframe: str, source_id: str) -> tuple[str, ...]:
        from strategy_factory.stages.optimize import stage2_selection_symbols
        from strategy_factory.stages.screen import stage1_pass_symbols

        reader = stage1_pass_symbols if stage == S01 else stage2_selection_symbols
        if stage not in (S01, S02):
            raise ConfigError(f"no stage reads the output of {stage}")
        return reader(self.root, run_id, (timeframe,), source_id)


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def funnel_hashes(cfg: FunnelConfig) -> Hashes:
    from strategy_factory.stages import edge, optimize_config, screen_config
    from strategy_factory.stages.config import load_s01_config

    return Hashes(
        stage_config={
            "s01_edge": edge.stage_config_hash(load_s01_config()),
            "s02_screen": screen_config.stage_config_hash(screen_config.load_s02_config()),
            "s03_entry": optimize_config.stage_config_hash(optimize_config.load_s03_config()),
        },
        gates=_file_sha(cfg.gates),
        code_version=code_version(),
    )


def build_source(cfg: FunnelConfig, runner: DefaultRunner) -> SourceRef | None:
    """The synthetic source of a funnel run (D-654): the generator settings in full and, for a
    planted run, the assignment of every symbol of every timeframe's scope (D-665)."""
    from strategy_factory.synthetic.config import (
        DEFAULT_NULL_CONFIG,
        DEFAULT_PLANTED_CONFIG,
        load_null_config,
        load_planted_config,
    )
    from strategy_factory.synthetic.planted import assign

    spec = cfg.source
    if spec.kind == "real":
        return None
    seed = cfg.seed if spec.seed is None else spec.seed
    if spec.kind == "null":
        null = load_null_config(spec.generator or DEFAULT_NULL_CONFIG)
        return SourceRef(kind="null", seed=seed, generator=null.model_dump(mode="json"))
    planted = load_planted_config(spec.generator or DEFAULT_PLANTED_CONFIG)
    symbols = sorted({s for tf in cfg.timeframes for s in runner.scope(cfg, tf)})
    planted = planted.model_copy(update={"assignment": assign(symbols, planted, seed)})
    return SourceRef(kind="planted", seed=seed, generator=planted.model_dump(mode="json"))


def write_truth(
    result: FunnelResult, cfg: FunnelConfig, runner: DefaultRunner, folder: Path
) -> Path:
    """``truth.json``: per timeframe and symbol, the cell and the planted positions (UTC
    microseconds) of the synthetic series the funnel ran on."""
    from strategy_factory.synthetic.access import SyntheticDataAccess

    assert result.source is not None
    splits = SplitManager(
        RegistryLedger(make_engine()), load_split_config(), runner.store, runner.catalog
    )
    data = SyntheticDataAccess(splits, result.source)
    out: dict[str, Any] = {"source": result.source.id, "timeframes": {}}
    for tf in cfg.timeframes:
        per: dict[str, Any] = {}
        for sym in runner.scope(cfg, tf):
            try:
                truth, ts = data.truth(sym, tf)
            except (DataError, ConfigError) as exc:  # e.g. too short for a split (D-008)
                per[sym] = {"error": str(exc)}
                continue
            per[sym] = truth.as_json(ts)
        out["timeframes"][tf] = per
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "truth.json"
    path.write_text(json.dumps(out, sort_keys=True), encoding="utf-8", newline="\n")
    return path


def run_funnel(
    config_path: Path,
    *,
    no_control: bool = False,
    fresh: bool = False,
    workers: int | None = None,
    notes: str = "",
) -> tuple[FunnelResult, Path]:
    cfg = load_funnel_config(config_path)
    executor = None
    if workers is not None:
        ex_cfg = load_executor_config().model_copy(update={"workers": workers, "numba_threads": 1})
        executor = make_executor(ex_cfg)
    runner = DefaultRunner(executor)
    source = build_source(cfg, runner)
    funnel = Funnel(
        cfg, FunnelRegistry(make_engine()), runner, funnel_hashes(cfg), source, notes=notes
    )
    result = funnel.run(control=not no_control, fresh=fresh)
    folder = funnel_folder(runner.root, result.funnel_id)
    write_funnel_summary(result, folder)
    if source is not None:
        write_truth(result, cfg, runner, folder)
    if cfg.report:
        write_funnel_report(result.funnel_id)
    return result, folder


def write_funnel_report(funnel_id: str, config: Path | None = None) -> Path:
    """``<artifacts>/funnels/<funnel_id>/report.html`` (D-655), from the artifacts only."""
    import uuid

    from strategy_factory.reports.config import load_report_config
    from strategy_factory.reports.read import read_funnel
    from strategy_factory.reports.render import write_report

    row = FunnelRegistry(make_engine()).funnel(uuid.UUID(funnel_id))
    ctx = read_funnel(funnel_id, artifacts_root(), row)
    return write_report(ctx, load_report_config(config))


def reproduce(funnel_id: str, workers: int | None = None) -> Any:
    """``sfac funnel reproduce``: see :mod:`strategy_factory.pipeline.funnel_reproduce`."""
    import uuid

    from sqlalchemy import select

    from strategy_factory.pipeline.funnel_reproduce import reproduce_funnel
    from strategy_factory.registry.tables import pipeline_runs

    engine = make_engine()
    registry = FunnelRegistry(engine)
    row = registry.funnel(uuid.UUID(funnel_id))
    cfg = FunnelConfig.model_validate(row["config"]["funnel"])
    executor = None
    if workers is not None:
        ex_cfg = load_executor_config().model_copy(update={"workers": workers, "numba_threads": 1})
        executor = make_executor(ex_cfg)
    runner = DefaultRunner(executor)

    def run_config(run_id: str) -> dict[str, Any]:
        with engine.connect() as conn:
            value = conn.execute(
                select(pipeline_runs.c.config).where(pipeline_runs.c.id == uuid.UUID(run_id))
            ).scalar_one()
        return dict(value)

    def truth(result: FunnelResult) -> Path | None:
        return write_truth(result, cfg, runner, funnel_folder(runner.root, result.funnel_id))

    report, new = reproduce_funnel(
        funnel_id,
        registry=registry,
        runner=runner,
        hashes=funnel_hashes(cfg),
        artifacts=runner.root,
        run_config=run_config,
        truth=truth,
    )
    write_funnel_summary(new, funnel_folder(runner.root, new.funnel_id))
    return report
