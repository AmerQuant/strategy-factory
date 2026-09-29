"""Stage-3 test helpers (T14): a real stage-1 and stage-2 run on synthetic data, then a stage-3
context. Stage 3 reads the stage-2 run's own artifacts (index + ``summary.json``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from fixtures.edge_stage import GATES, FakeData, FakeReferences, resolved_config
from fixtures.screen_stage import screen_config_file, screen_context, stage1_run
from strategy_factory.core.config import PipelineConfig
from strategy_factory.gates.engine import GateEngine
from strategy_factory.pipeline.executor import SerialExecutor
from strategy_factory.stages.base import RunContext
from strategy_factory.stages.optimize_config import load_s03_config
from strategy_factory.stages.screen import ScreenStage

S02_RUN = "dry-run"  # ScreenStage writes a run without an id under "dry-run"


def stage2_run(
    root: Path,
    series: dict[Any, Any],
    symbols: tuple[str, ...],
    registry: Any = None,
    run_ids: tuple[Any, Any] = (None, None),
    **screen_updates: Any,
) -> Path:
    """Stage 1, then stage 2 on its passes; returns the stage-2 run folder."""
    stage1_run(root, series, symbols, registry=registry, run_id=run_ids[0])
    ctx = screen_context(
        root,
        series,
        symbols,
        registry=registry,
        run_id=run_ids[1],
        s01_run=str(run_ids[0]) if run_ids[0] else "dry-run",
    )
    ScreenStage(stage_config_path=screen_config_file(root, **screen_updates)).run(
        [(s, "1D") for s in symbols], ctx
    )
    return root / (str(run_ids[1]) if run_ids[1] else S02_RUN) / "s02_screen"


def entry_config_file(root: Path, **updates: Any) -> Path:
    """The real stage-3 config with any top-level (or ``fine_grid``) ``updates``."""
    cfg = load_s03_config()
    data = cfg.model_dump(mode="json", exclude={"exits"})
    grid = updates.pop("fine_grid", None)
    if grid:
        data["fine_grid"].update(grid)
    data.update(updates)
    path = root / "s03.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def entry_context(
    root: Path,
    series: dict[Any, Any],
    symbols: tuple[str, ...],
    *,
    control: str = "none",
    executor: Any = None,
    registry: Any = None,
    run_id: Any = None,
    hashes: dict[tuple[str, str], str] | None = None,
    s02_run: str = S02_RUN,
) -> RunContext:
    base = resolved_config(symbols, control=control)
    cfg = PipelineConfig.model_validate(
        {
            **base.model_dump(),
            "stages": ("s03_entry",),
            "stage_inputs": {"s02_screen": s02_run},
        }
    )
    if hashes:
        snaps = {s: dict(v) for s, v in cfg.data_snapshots.items()}
        for (s, tf), h in hashes.items():
            snaps[s][tf] = snaps[s][tf].model_copy(update={"snapshot_hash": h})
        cfg = cfg.model_copy(update={"data_snapshots": snaps})
    return RunContext(
        config=cfg,
        data=FakeData(series),  # type: ignore[arg-type]
        references=FakeReferences(  # type: ignore[arg-type]
            {(s, "1D"): base.data_snapshots[s]["1D"].snapshot_hash for s in symbols}
        ),
        executor=executor or SerialExecutor(),
        gates=GateEngine.from_file(GATES),
        artifacts_root=root,
        code_version="test",
        registry=registry,
        run_id=run_id,
    )
