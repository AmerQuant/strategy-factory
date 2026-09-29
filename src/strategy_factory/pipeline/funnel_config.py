"""The funnel config (F-0.8.2, T15a §3): one file runs stages 1 -> 2 -> 3 with the control.

``configs/funnel/<name>.yaml``; defaults here (rule 1). The orchestrator builds every stage run's
``PipelineConfig`` from it -- the same fields the hand-written ``configs/pipeline/s0*_*.yaml``
carry, with ``stage_inputs`` set to the upstream stage run -- so a stage run inside a funnel is an
ordinary registry run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from strategy_factory.core.errors import ConfigError

#: the MVP funnel's stages, in order (T15a §3); a funnel runs a prefix of them
FUNNEL_STAGES = ("s01_edge", "s02_screen", "s03_entry")


class SourceSpec(BaseModel):
    """D-654: where the bars come from. ``null`` / ``planted`` name their generator config; the
    orchestrator stores the validated settings in full in every stage run's config (D-670)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["real", "null", "planted"] = "real"
    seed: int = 0
    generator: Path | None = None  # default: configs/synthetic/<kind>.yaml


class FunnelConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceSpec = Field(default_factory=SourceSpec)
    symbol_scope: Literal["broker", "listed"] = "broker"  # D-616, as stage 1
    symbols: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = Field(min_length=1)
    stages: tuple[str, ...] = FUNNEL_STAGES
    control: bool = True  # D-653: the reshuffled-returns control runs alongside by default
    seed: int = 42
    report: bool = True  # D-655: one report per funnel run
    universe: Path = Path("configs") / "universe.yaml"
    gates: Path = Path("configs") / "gates" / "default.yaml"

    @field_validator("stages")
    @classmethod
    def _prefix(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or value != FUNNEL_STAGES[: len(value)]:
            raise ValueError(f"stages must be a prefix of {list(FUNNEL_STAGES)}, got {list(value)}")
        return value

    @field_validator("timeframes", "symbols")
    @classmethod
    def _unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError(f"duplicate entries in {list(value)}")
        return value

    def canonical(self) -> dict[str, object]:
        data = self.model_dump(mode="json")
        data["universe"] = self.universe.as_posix()
        data["gates"] = self.gates.as_posix()
        return data


def load_funnel_config(path: Path) -> FunnelConfig:
    if not path.is_file():
        raise ConfigError("funnel config not found", config_path=path)
    try:
        cfg = FunnelConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read funnel config: {exc}", config_path=path) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid funnel config: {exc}", config_path=path) from exc
    if cfg.symbol_scope == "listed" and not cfg.symbols:
        raise ConfigError("symbol_scope listed needs symbols", config_path=path)
    return cfg
