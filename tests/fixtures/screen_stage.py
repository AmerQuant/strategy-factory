"""Stage-2 test helpers (T13): a real stage-1 run on synthetic data, then a stage-2 context.

Stage 2 reads the stage-1 run's own artifacts (index + ``summary.json``), so the helpers run
:class:`EdgeStage` first on planted-edge series (``phi < 0``: mean reversion) and hand
:class:`ScreenStage` the same fake data and references.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from fixtures.edge_stage import (
    GATES,
    FakeData,
    FakeReferences,
    resolved_config,
    stage_config,
    synthetic_bars,
)
from strategy_factory.core.config import PipelineConfig
from strategy_factory.gates.engine import GateEngine
from strategy_factory.pipeline.executor import SerialExecutor
from strategy_factory.stages.base import RunContext
from strategy_factory.stages.edge import EdgeStage
from strategy_factory.stages.screen_config import load_s02_config

REPO = Path(__file__).resolve().parents[2]
S01_RUN = "dry-run"  # EdgeStage writes a run without an id under "dry-run"


def planted_series(symbols: tuple[str, ...], n: int = 1200, phi: float = -0.35) -> dict[Any, Any]:
    return {(s, "1D"): synthetic_bars(n, i, phi=phi) for i, s in enumerate(symbols)}


def stage1_run(
    root: Path,
    series: dict[Any, Any],
    symbols: tuple[str, ...],
    registry: Any = None,
    run_id: Any = None,
) -> Path:
    """Run stage 1 on ``series`` into ``root/<run id or dry-run>/s01_edge``; returns it."""
    cfg = resolved_config(symbols)
    ctx = RunContext(
        config=cfg,
        data=FakeData(series),  # type: ignore[arg-type]
        references=FakeReferences(  # type: ignore[arg-type]
            {(s, "1D"): cfg.data_snapshots[s]["1D"].snapshot_hash for s in symbols}
        ),
        executor=SerialExecutor(),
        gates=GateEngine.from_file(GATES),
        artifacts_root=root,
        code_version="test",
        registry=registry,
        run_id=run_id,
    )
    root.mkdir(parents=True, exist_ok=True)
    s01 = root / "s01.yaml"
    s01.write_text(
        yaml.safe_dump(stage_config(simulations=100).model_dump(mode="json")), encoding="utf-8"
    )
    EdgeStage(stage_config_path=s01).run([(s, "1D") for s in symbols], ctx)
    return root / (str(run_id) if run_id else S01_RUN) / "s01_edge"


def screen_config_file(root: Path, simulations: int = 100, **updates: Any) -> Path:
    """The real stage-2 config with fewer baseline draws (and any top-level ``updates``)."""
    cfg = load_s02_config()
    data = cfg.model_dump(mode="json", exclude={"exits"})
    data["baseline"]["simulations"] = simulations
    data.update(updates)
    path = root / "s02.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def screen_context(
    root: Path,
    series: dict[Any, Any],
    symbols: tuple[str, ...],
    *,
    control: str = "none",
    executor: Any = None,
    registry: Any = None,
    run_id: Any = None,
    hashes: dict[tuple[str, str], str] | None = None,
    s01_run: str = S01_RUN,
) -> RunContext:
    base = resolved_config(symbols, control=control)
    cfg = PipelineConfig.model_validate(
        {
            **base.model_dump(),
            "stages": ("s02_screen",),
            "stage_inputs": {"s01_edge": s01_run},
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
