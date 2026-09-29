"""``sfac run``: a minimal driver for stage 1 (D-616). The orchestrator stays T15 (F-X.1).

Builds the :class:`~stages.base.RunContext` -- the resolved config, the development-only
``DataAccess``, the read-only reference view, the executor, the gates, the artifacts root --
records the run in the registry (``pipeline_runs``: config, seed, code version) and runs
``s01_edge`` over every (symbol, timeframe) of the config. The split manager is built here,
**outside** the stage modules, and handed to the stage only inside ``DataAccess`` (D-616).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from strategy_factory.core.config import load_pipeline_config, resolve_config, start_run
from strategy_factory.core.env import resolve_env
from strategy_factory.core.errors import ConfigError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import load_split_config
from strategy_factory.data.split import DataAccess, RegistryLedger, SplitManager
from strategy_factory.data.store import SnapshotStore
from strategy_factory.gates.engine import GateEngine
from strategy_factory.pipeline.executor import load_executor_config, make_executor
from strategy_factory.pipeline.qos import opt_out_of_efficiency_mode
from strategy_factory.registry.engine import make_engine
from strategy_factory.registry.writer import RegistryWriter, code_version
from strategy_factory.stages.base import RunContext, StageResult
from strategy_factory.stages.config import STAGE
from strategy_factory.stages.edge import EdgeStage
from strategy_factory.stages.reference import ReferenceInfo

ARTIFACTS_ENV = "SFAC_ARTIFACTS_ROOT"


@dataclass(frozen=True)
class RunReport:
    run_id: str
    artifacts: Path
    result: StageResult
    seconds: float
    symbols: int
    excluded: dict[str, str]


def artifacts_root() -> Path:
    value, _ = resolve_env((ARTIFACTS_ENV,))[ARTIFACTS_ENV]
    if not value:
        raise ConfigError(f"{ARTIFACTS_ENV} is not set: define it in the environment or .env")
    return Path(value)


def run_config(config_path: Path, notes: str = "", executor: Any = None) -> RunReport:
    """``sfac run``: one stage per config -- ``s01_edge`` (D-616), ``s02_screen`` (T13) or
    ``s03_entry`` (T14)."""
    from strategy_factory.stages.optimize_config import STAGE as S03
    from strategy_factory.stages.screen_config import STAGE as S02

    stages = tuple(load_pipeline_config(config_path).stages)
    if stages == (S02,):
        return run_stage2(config_path, notes=notes, executor=executor)
    if stages == (S03,):
        return run_stage3(config_path, notes=notes, executor=executor)
    return run_stage1(config_path, notes=notes, executor=executor)


def run_stage3(config_path: Path, notes: str = "", executor: Any = None) -> RunReport:
    """Stage 3 over the selections of the stage-2 run named in ``stage_inputs`` (T14 §3).

    ``symbol_scope: stage_inputs`` expands to the symbols of those selections before resolution;
    the stage then refuses a candidate whose reference moved since stage 2. A control config
    (``control: random_walk``) reruns the **real** selections on reshuffled bars (D-651 (b)).
    """
    from strategy_factory.stages.optimize import EntryStage, stage2_selection_symbols
    from strategy_factory.stages.optimize_config import STAGE as S03
    from strategy_factory.stages.screen_config import STAGE as S02

    cfg = load_pipeline_config(config_path)
    if tuple(cfg.stages) != (S03,):
        raise ConfigError(f"run_stage3 runs {S03} only; the config lists {list(cfg.stages)}")
    if S02 not in cfg.stage_inputs:
        raise ConfigError(f"{S03} needs stage_inputs.{S02}", config_path=config_path)
    executor_cfg = load_executor_config()
    opt_out_of_efficiency_mode(executor_cfg.efficiency_mode_opt_out)  # D-804
    root = artifacts_root()
    if cfg.symbol_scope == "stage_inputs":
        symbols = stage2_selection_symbols(root, cfg.stage_inputs[S02], cfg.timeframes)
        if not symbols:
            raise ConfigError(
                f"stage-2 run {cfg.stage_inputs[S02]} has no selection on {list(cfg.timeframes)}"
            )
        cfg = cfg.model_copy(update={"symbols": symbols})
    store = SnapshotStore()
    catalog = Catalog(store.root)
    cfg = resolve_config(cfg, catalog_root=store.root, config_path=config_path)
    engine = make_engine()
    writer = RegistryWriter(engine)
    version = code_version()
    run_id = start_run(cfg, writer, notes=notes or f"{S03} control={cfg.control}")
    splits = SplitManager(RegistryLedger(engine), load_split_config(), store, catalog)
    ctx = RunContext(
        config=cfg,
        data=DataAccess(splits),
        references=ReferenceInfo(catalog),
        executor=executor if executor is not None else make_executor(executor_cfg),
        gates=GateEngine.from_file(cfg.gates),
        artifacts_root=root,
        code_version=version,
        registry=writer,
        run_id=run_id,
    )
    inputs = [(sym, tf) for tf in cfg.timeframes for sym in cfg.symbols]
    started = dt.datetime.now(dt.UTC)
    try:
        result = EntryStage().run(inputs, ctx)
    except BaseException:
        writer.finish_run(run_id, "failed")
        raise
    writer.finish_run(run_id, "done")
    return RunReport(
        run_id=str(run_id),
        artifacts=ctx.artifacts_root / str(run_id) / S03,
        result=result,
        seconds=(dt.datetime.now(dt.UTC) - started).total_seconds(),
        symbols=len(cfg.symbols),
        excluded=dict(cfg.scope_excluded),
    )


def run_stage2(config_path: Path, notes: str = "", executor: Any = None) -> RunReport:
    """Stage 2 over the passes of the stage-1 run named in ``stage_inputs`` (T13 §3).

    ``symbol_scope: stage_inputs`` expands to the symbols of those passes before resolution, so
    the resolved config (and its hash) names exactly what ran; the stage then refuses a profile
    whose reference moved since stage 1.
    """
    from strategy_factory.stages.config import STAGE as S01
    from strategy_factory.stages.screen import ScreenStage, stage1_pass_symbols
    from strategy_factory.stages.screen_config import STAGE as S02

    cfg = load_pipeline_config(config_path)
    if tuple(cfg.stages) != (S02,):
        raise ConfigError(f"run_stage2 runs {S02} only; the config lists {list(cfg.stages)}")
    if S01 not in cfg.stage_inputs:
        raise ConfigError(f"{S02} needs stage_inputs.{S01}", config_path=config_path)
    executor_cfg = load_executor_config()
    opt_out_of_efficiency_mode(executor_cfg.efficiency_mode_opt_out)  # D-804
    root = artifacts_root()
    if cfg.symbol_scope == "stage_inputs":
        symbols = stage1_pass_symbols(root, cfg.stage_inputs[S01], cfg.timeframes)
        if not symbols:
            raise ConfigError(
                f"stage-1 run {cfg.stage_inputs[S01]} has no pass on {list(cfg.timeframes)}"
            )
        cfg = cfg.model_copy(update={"symbols": symbols})
    store = SnapshotStore()
    catalog = Catalog(store.root)
    cfg = resolve_config(cfg, catalog_root=store.root, config_path=config_path)
    engine = make_engine()
    writer = RegistryWriter(engine)
    version = code_version()
    run_id = start_run(cfg, writer, notes=notes or f"{S02} control={cfg.control}")
    splits = SplitManager(RegistryLedger(engine), load_split_config(), store, catalog)
    ctx = RunContext(
        config=cfg,
        data=DataAccess(splits),
        references=ReferenceInfo(catalog),
        executor=executor if executor is not None else make_executor(executor_cfg),
        gates=GateEngine.from_file(cfg.gates),
        artifacts_root=root,
        code_version=version,
        registry=writer,
        run_id=run_id,
    )
    inputs = [(sym, tf) for tf in cfg.timeframes for sym in cfg.symbols]
    started = dt.datetime.now(dt.UTC)
    try:
        result = ScreenStage().run(inputs, ctx)
    except BaseException:
        writer.finish_run(run_id, "failed")
        raise
    writer.finish_run(run_id, "done")
    return RunReport(
        run_id=str(run_id),
        artifacts=ctx.artifacts_root / str(run_id) / S02,
        result=result,
        seconds=(dt.datetime.now(dt.UTC) - started).total_seconds(),
        symbols=len(cfg.symbols),
        excluded=dict(cfg.scope_excluded),
    )


def run_stage1(config_path: Path, notes: str = "", executor: Any = None) -> RunReport:
    cfg = load_pipeline_config(config_path)
    if tuple(cfg.stages) != (STAGE,):
        raise ConfigError(
            f"sfac run executes stage 1 only for now (D-616); the config lists {list(cfg.stages)}",
            config_path=config_path,
        )
    executor_cfg = load_executor_config()
    opt_out_of_efficiency_mode(executor_cfg.efficiency_mode_opt_out)  # D-804: the parent too
    store = SnapshotStore()
    catalog = Catalog(store.root)
    cfg = resolve_config(cfg, catalog_root=store.root, config_path=config_path)
    engine = make_engine()
    writer = RegistryWriter(engine)
    version = code_version()
    run_id = start_run(cfg, writer, notes=notes or f"s01_edge control={cfg.control}")
    splits = SplitManager(RegistryLedger(engine), load_split_config(), store, catalog)
    ctx = RunContext(
        config=cfg,
        data=DataAccess(splits),
        references=ReferenceInfo(catalog),
        executor=executor if executor is not None else make_executor(executor_cfg),
        gates=GateEngine.from_file(cfg.gates),
        artifacts_root=artifacts_root(),
        code_version=version,
        registry=writer,
        run_id=run_id,
    )
    inputs = [(sym, tf) for tf in cfg.timeframes for sym in cfg.symbols]
    started = dt.datetime.now(dt.UTC)
    try:
        result = EdgeStage().run(inputs, ctx)
    except BaseException:
        writer.finish_run(run_id, "failed")
        raise
    writer.finish_run(run_id, "done")
    return RunReport(
        run_id=str(run_id),
        artifacts=ctx.artifacts_root / str(run_id) / STAGE,
        result=result,
        seconds=(dt.datetime.now(dt.UTC) - started).total_seconds(),
        symbols=len(cfg.symbols),
        excluded=dict(cfg.scope_excluded),
    )
