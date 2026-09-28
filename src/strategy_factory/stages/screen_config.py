"""Stage-2 configuration (``configs/stages/s02_screen.yaml``; T13, rule 1).

Validated against the component registry when it loads: every listed method is a registered
stage-2 method (``screen = True``) of its edge type, and **every** registered stage-2 method of
a listed edge type is listed (the library cannot silently lose a method). The exits are stage
1's (D-622), read from ``s01_edge.yaml``; they are part of the stage-config hash.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from strategy_factory.components.registry import default_registry
from strategy_factory.core.config import canonical_json
from strategy_factory.core.errors import ConfigError
from strategy_factory.metrics.family import FamilyScoreConfig
from strategy_factory.stages.config import EdgeTypeSpec, load_s01_config

#: The stage id: the gate stage, the artifacts folder and the trials' stage (D-354 (2)).
STAGE = "s02_screen"
DEFAULT_PATH = Path("configs") / "stages" / "s02_screen.yaml"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BaselineSpec(_Frozen):
    simulations: int = Field(ge=1)

    @property
    def p_floor(self) -> float:
        return 1.0 / (self.simulations + 1)


class SelectionSpec(_Frozen):
    min_candidates: int = Field(ge=1)
    max_candidates: int = Field(ge=1)


class S02ScreenConfig(_Frozen):
    methods: dict[str, tuple[str, ...]] = Field(min_length=1)
    good_region_share: float = Field(gt=0, le=1)
    baseline: BaselineSpec
    family_score: FamilyScoreConfig
    selection: SelectionSpec
    #: D-621: passes on these timeframes go through flagged `unconfirmed` and are reported apart
    unconfirmed_timeframes: tuple[str, ...] = ()
    batch_units: int = Field(ge=1)
    #: stage 1's fixed exits per edge type (D-622), filled from s01_edge.yaml at load time
    exits: dict[str, EdgeTypeSpec] = Field(default_factory=dict)

    def methods_of(self, edge_type: str) -> tuple[str, ...]:
        return tuple(sorted(self.methods.get(edge_type, ())))


def check_against_registry(cfg: S02ScreenConfig) -> list[str]:
    reg = default_registry()
    problems: list[str] = []
    screen = {c.name: c for c in reg.entries() if getattr(c, "screen", False)}
    for edge, names in cfg.methods.items():
        if edge not in cfg.exits:
            problems.append(f"edge type {edge!r} has no stage-1 exits (s01_edge.yaml)")
        if len(set(names)) != len(names):
            problems.append(f"{edge}: duplicate methods")
        for name in names:
            comp = screen.get(name)
            if comp is None:
                problems.append(f"{name!r} is not a registered stage-2 method")
            elif comp.edge_type != edge:
                problems.append(f"{name!r} is of edge type {comp.edge_type}, listed under {edge}")
    for name, comp in sorted(screen.items()):
        if comp.edge_type in cfg.methods and name not in cfg.methods[comp.edge_type]:
            problems.append(f"registered stage-2 method {name!r} is missing from the config")
    if cfg.selection.min_candidates > cfg.selection.max_candidates:
        problems.append("selection: min_candidates > max_candidates")
    return problems


def load_s02_config(path: Path | None = None, s01_path: Path | None = None) -> S02ScreenConfig:
    target = path if path is not None else DEFAULT_PATH
    if not target.is_file():
        raise ConfigError("stage-2 config not found", config_path=target)
    try:
        data: dict[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if "exits" in data:
            raise ConfigError(
                "the stage-2 exits are stage 1's (D-622): remove 'exits' from the stage-2 config",
                config_path=target,
            )
        data["exits"] = load_s01_config(s01_path).edge_types
        cfg = S02ScreenConfig.model_validate(data)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read the stage-2 config: {exc}", config_path=target) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid stage-2 config: {exc}", config_path=target) from exc
    problems = check_against_registry(cfg)
    if problems:
        raise ConfigError("stage-2 config invalid: " + "; ".join(problems), config_path=target)
    return cfg


def stage_config_hash(cfg: S02ScreenConfig) -> str:
    """sha256 of the whole stage config, the stage-1 exits included (D-805's pattern)."""
    return hashlib.sha256(canonical_json(cfg.model_dump(mode="json")).encode("utf-8")).hexdigest()
