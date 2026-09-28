"""The stage framework (design §4, as amended by D-616).

A stage is ``Stage.run(inputs, ctx) -> StageResult`` and touches data and the registry only
through :class:`RunContext`.

**Deviation from design §4 (D-616):** ``RunContext`` exposes :class:`DataAccess` (the
development segment only) and a read-only :class:`ReferenceInfo`, and **never** a
``SplitManager``: the holdout is stage 6's (D-306), so no stage built on this context can
reach ``open_holdout``. A static test asserts that the stage modules neither import
``SplitManager`` nor mention ``open_holdout``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from strategy_factory.core.config import PipelineConfig
from strategy_factory.data.split import DataAccess
from strategy_factory.gates.engine import GateEngine, GateResult
from strategy_factory.pipeline.executor import Executor
from strategy_factory.stages.reference import ReferenceInfo


@dataclass(frozen=True)
class ArtifactRef:
    kind: str
    path: Path
    candidate_id: str | None
    sha256: str
    schema_version: str


@dataclass
class StageResult:
    artifacts: list[ArtifactRef] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)  # candidate ids that pass the stage gate
    gate_results: list[GateResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunContext:
    """Everything a stage may use. There is deliberately no split manager here (D-616)."""

    config: PipelineConfig  # resolved (data snapshots and cost inputs pinned)
    data: DataAccess
    references: ReferenceInfo
    executor: Executor
    gates: GateEngine
    artifacts_root: Path
    code_version: str
    registry: Any = None  # a RegistryWriter, or None for a dry run (no registry rows)
    run_id: uuid.UUID | None = None

    @property
    def seed(self) -> int:
        return self.config.seed


class Stage(Protocol):
    name: str

    def run(self, inputs: Sequence[Any], ctx: RunContext) -> StageResult: ...
