"""``sfac run``: one stage per config -- ``s01_edge`` (D-616), ``s02_screen`` (T13), ``s03_entry``
(T14). The funnel (``pipeline/funnel.py``, T15a) calls the same entry point for every stage run.

Builds the :class:`~stages.base.RunContext` -- the resolved config, the development-only
``DataAccess`` (or, for a synthetic source, ``SyntheticDataAccess``, D-654), the read-only
reference view, the executor, the gates, the artifacts root -- records the run in the registry
(``pipeline_runs``: config, seed, code version, source) and runs the stage over every (symbol,
timeframe) of the config. The split manager is built here, **outside** the stage modules, and
handed to the stage only inside ``DataAccess`` (D-616).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from strategy_factory.core.config import (
    PipelineConfig,
    load_pipeline_config,
    resolve_config,
    start_run,
)
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
    return run_pipeline_config(
        load_pipeline_config(config_path),
        notes=notes,
        executor=executor,
        config_path=config_path,
    )


def run_pipeline_config(
    cfg: PipelineConfig,
    notes: str = "",
    executor: Any = None,
    config_path: Path | None = None,
    on_start: Callable[[str], None] | None = None,
) -> RunReport:
    """Run the one stage ``cfg`` names; the config may be built in memory (the funnel).
    ``on_start`` receives the registry run id as soon as the run row exists."""
    from strategy_factory.stages.optimize_config import STAGE as S03
    from strategy_factory.stages.screen_config import STAGE as S02

    stages = tuple(cfg.stages)
    if stages == (S02,):
        return _run(cfg, S02, notes, executor, config_path, on_start)
    if stages == (S03,):
        return _run(cfg, S03, notes, executor, config_path, on_start)
    if stages == (STAGE,):
        return _run(cfg, STAGE, notes, executor, config_path, on_start)
    raise ConfigError(
        f"sfac run executes one stage per config (s01_edge, s02_screen or s03_entry); the config "
        f"lists {list(cfg.stages)}",
        config_path=config_path,
    )


def run_stage3(config_path: Path, notes: str = "", executor: Any = None) -> RunReport:
    """Stage 3 over the selections of the stage-2 run named in ``stage_inputs`` (T14 §3).

    ``symbol_scope: stage_inputs`` expands to the symbols of those selections before resolution;
    the stage then refuses a candidate whose reference moved since stage 2. A control config
    (``control: random_walk``) reruns the **real** selections on reshuffled bars (D-651 (b)).
    """
    from strategy_factory.stages.optimize_config import STAGE as S03

    cfg = load_pipeline_config(config_path)
    if tuple(cfg.stages) != (S03,):
        raise ConfigError(f"run_stage3 runs {S03} only; the config lists {list(cfg.stages)}")
    return _run(cfg, S03, notes, executor, config_path, None)


def run_stage2(config_path: Path, notes: str = "", executor: Any = None) -> RunReport:
    """Stage 2 over the passes of the stage-1 run named in ``stage_inputs`` (T13 §3).

    ``symbol_scope: stage_inputs`` expands to the symbols of those passes before resolution, so
    the resolved config (and its hash) names exactly what ran; the stage then refuses a profile
    whose reference moved since stage 1.
    """
    from strategy_factory.stages.screen_config import STAGE as S02

    cfg = load_pipeline_config(config_path)
    if tuple(cfg.stages) != (S02,):
        raise ConfigError(f"run_stage2 runs {S02} only; the config lists {list(cfg.stages)}")
    return _run(cfg, S02, notes, executor, config_path, None)


def run_stage1(config_path: Path, notes: str = "", executor: Any = None) -> RunReport:
    cfg = load_pipeline_config(config_path)
    if tuple(cfg.stages) != (STAGE,):
        raise ConfigError(
            f"sfac run executes stage 1 only for now (D-616); the config lists {list(cfg.stages)}",
            config_path=config_path,
        )
    return _run(cfg, STAGE, notes, executor, config_path, None)


def expand_stage_inputs(cfg: PipelineConfig, stage: str, root: Path) -> PipelineConfig:
    """``symbol_scope: stage_inputs`` -> the symbols of the upstream run's passes or selections
    (T13 §3, T14 §3), read with the run's own source so real and synthetic never mix (D-654)."""
    from strategy_factory.stages.config import STAGE as S01
    from strategy_factory.stages.optimize import stage2_selection_symbols
    from strategy_factory.stages.optimize_config import STAGE as S03
    from strategy_factory.stages.screen import stage1_pass_symbols
    from strategy_factory.stages.screen_config import STAGE as S02

    upstream = {S02: S01, S03: S02}.get(stage)
    if upstream is None:
        return cfg
    if upstream not in cfg.stage_inputs:
        raise ConfigError(f"{stage} needs stage_inputs.{upstream}")
    if cfg.symbol_scope != "stage_inputs":
        return cfg
    reader = stage1_pass_symbols if stage == S02 else stage2_selection_symbols
    what = "pass" if stage == S02 else "selection"
    symbols = reader(root, cfg.stage_inputs[upstream], cfg.timeframes, cfg.source_id)
    if not symbols:
        raise ConfigError(
            f"{upstream} run {cfg.stage_inputs[upstream]} has no {what} on {list(cfg.timeframes)}"
        )
    return cfg.model_copy(update={"symbols": symbols})


def data_access(cfg: PipelineConfig, splits: SplitManager) -> DataAccess:
    """The run's bars: the real development segment, or its synthetic version (D-654)."""
    if cfg.source is None:
        return DataAccess(splits)
    from strategy_factory.synthetic.access import SyntheticDataAccess

    return SyntheticDataAccess(splits, cfg.source)


def _stage(stage: str) -> Any:
    from strategy_factory.stages.edge import EdgeStage
    from strategy_factory.stages.optimize import EntryStage
    from strategy_factory.stages.optimize_config import STAGE as S03
    from strategy_factory.stages.screen import ScreenStage
    from strategy_factory.stages.screen_config import STAGE as S02

    return {STAGE: EdgeStage, S02: ScreenStage, S03: EntryStage}[stage]()


def _run(
    cfg: PipelineConfig,
    stage: str,
    notes: str,
    executor: Any,
    config_path: Path | None,
    on_start: Callable[[str], None] | None,
) -> RunReport:
    executor_cfg = load_executor_config()
    opt_out_of_efficiency_mode(executor_cfg.efficiency_mode_opt_out)  # D-804: the parent too
    root = artifacts_root()
    cfg = expand_stage_inputs(cfg, stage, root)
    store = SnapshotStore()
    catalog = Catalog(store.root)
    cfg = resolve_config(cfg, catalog_root=store.root, config_path=config_path)
    engine = make_engine()
    writer = RegistryWriter(engine)
    version = code_version()
    run_id = start_run(
        cfg, writer, notes=notes or f"{stage} control={cfg.control} source={cfg.source_id}"
    )
    if on_start is not None:
        on_start(str(run_id))
    splits = SplitManager(RegistryLedger(engine), load_split_config(), store, catalog)
    ctx = RunContext(
        config=cfg,
        data=data_access(cfg, splits),
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
        result = _stage(stage).run(inputs, ctx)
    except BaseException:
        writer.finish_run(run_id, "failed")
        raise
    writer.finish_run(run_id, "done")
    return RunReport(
        run_id=str(run_id),
        artifacts=ctx.artifacts_root / str(run_id) / stage,
        result=result,
        seconds=(dt.datetime.now(dt.UTC) - started).total_seconds(),
        symbols=len(cfg.symbols),
        excluded=dict(cfg.scope_excluded),
    )
