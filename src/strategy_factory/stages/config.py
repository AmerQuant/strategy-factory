"""Stage-1 configuration (``configs/stages/s01_edge.yaml``; T12, rule 1).

Validated against the component registry and the edge-type registry when it loads:

* every listed probe is a registered entry component with a group (F-1.1, F-1.2), of an edge
  type the stage runs, and **every** registered probe of those edge types is listed -- the
  battery cannot silently lose a probe;
* every applicable group is a group of its edge type (``configs/edges/edge_types.yaml``);
* an edge type with fewer than ``min_applicable_groups`` applicable groups is **not run**
  (D-233) -- :meth:`S01EdgeConfig.runnable_edge_types` leaves it out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from strategy_factory.components.edges import load_edge_types
from strategy_factory.components.registry import default_registry
from strategy_factory.core.errors import ConfigError
from strategy_factory.metrics.ess import EssConfig

#: The stage id: the gate stage of the profile, the artifacts folder and the trials' stage
#: (D-354 (2): a stage passes its id from its own constant).
STAGE = "s01_edge"
#: The per-probe gate stage (configs/gates/default.yaml).
PROBE_STAGE = "s01_probe"
DEFAULT_PATH = Path("configs") / "stages" / "s01_edge.yaml"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EdgeTypeSpec(_Frozen):
    applicable_groups: tuple[str, ...] = Field(min_length=1)
    exit_signal: Literal["prev_extreme", "reverse"]
    time_exit_bars: int = Field(ge=1)


class ProbeSpec(_Frozen):
    warmup_bars: int = Field(ge=0)


class BaselineSpec(_Frozen):
    simulations: int = Field(ge=1)

    @property
    def p_floor(self) -> float:
        """D-606: the empirical p is floored at ``1 / (simulations + 1)`` (1/1001)."""
        return 1.0 / (self.simulations + 1)


class S01EdgeConfig(_Frozen):
    min_applicable_groups: int = Field(ge=1)
    edge_types: dict[str, EdgeTypeSpec] = Field(min_length=1)
    probes: dict[str, ProbeSpec] = Field(min_length=1)
    baseline: BaselineSpec
    ess: EssConfig
    mean_median_divergence_warn_atr: float = Field(gt=0)

    def runnable_edge_types(self) -> tuple[str, ...]:
        """The edge types with enough applicable groups to be run (D-233), sorted."""
        return tuple(
            sorted(
                name
                for name, spec in self.edge_types.items()
                if len(spec.applicable_groups) >= self.min_applicable_groups
            )
        )

    def probes_of(self, edge_type: str) -> tuple[str, ...]:
        """The listed probes of ``edge_type``, sorted by name (a stable battery order)."""
        reg = default_registry()
        return tuple(sorted(p for p in self.probes if reg.get(p).edge_type == edge_type))


def check_against_registry(cfg: S01EdgeConfig) -> list[str]:
    """Differences between the config and the component / edge-type registries."""
    reg = default_registry()
    edges = load_edge_types()
    problems: list[str] = []
    for name, spec in cfg.edge_types.items():
        if name not in edges.ids():
            problems.append(f"edge type {name!r} is not in the edge-type registry")
            continue
        unknown = set(spec.applicable_groups) - set(edges.get(name).group_ids())
        if unknown:
            problems.append(f"{name}: applicable groups {sorted(unknown)} are not groups of {name}")
    registered = {c.name: c for c in reg.entries() if c.group}
    for probe in cfg.probes:
        comp = registered.get(probe)
        if comp is None:
            problems.append(f"probe {probe!r} is not a registered entry with a group")
        elif comp.edge_type not in cfg.edge_types:
            problems.append(f"probe {probe!r} is of edge type {comp.edge_type}, not run by stage 1")
    for name, comp in sorted(registered.items()):
        if comp.edge_type in cfg.edge_types and name not in cfg.probes:
            problems.append(
                f"registered probe {name!r} ({comp.edge_type}) is missing from the config"
            )
    return problems


def load_s01_config(path: Path | None = None) -> S01EdgeConfig:
    target = path if path is not None else DEFAULT_PATH
    if not target.is_file():
        raise ConfigError("stage-1 config not found", config_path=target)
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        cfg = S01EdgeConfig.model_validate(data)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read the stage-1 config: {exc}", config_path=target) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid stage-1 config: {exc}", config_path=target) from exc
    problems = check_against_registry(cfg)
    if problems:
        raise ConfigError("stage-1 config invalid: " + "; ".join(problems), config_path=target)
    return cfg
