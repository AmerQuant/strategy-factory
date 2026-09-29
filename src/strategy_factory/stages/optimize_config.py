"""Stage-3 configuration (``configs/stages/s03_entry.yaml``; T14, rule 1).

The exits are stage 1's (D-622), read from ``s01_edge.yaml`` and part of the stage-config hash.
The trade minimum and the plateau cut are read from the gate YAML by the stage (T14 §4,
D-650 (f)); they are not restated here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from strategy_factory.core.config import canonical_json
from strategy_factory.core.errors import ConfigError
from strategy_factory.metrics.plateau import FailedCell
from strategy_factory.stages.config import EdgeTypeSpec, load_s01_config

#: The stage id: the gate stage, the artifacts folder and the trials' stage (D-354 (2)).
STAGE = "s03_entry"
DEFAULT_PATH = Path("configs") / "stages" / "s03_entry.yaml"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FineGridSpec(_Frozen):
    margin_coarse_steps: int = Field(ge=1)  # D-639
    max_cells: int = Field(ge=1)  # D-120, D-649
    max_free_params: int = Field(ge=1)  # D-120


class SppSpec(_Frozen):
    low: float = Field(gt=0, lt=50)
    high: float = Field(gt=50, lt=100)


class S03EntryConfig(_Frozen):
    fine_grid: FineGridSpec
    failed_cell: FailedCell  # D-646
    half_min_trades: Literal["full", "half"]  # D-647
    spp_percentiles: SppSpec
    small_grid_cells: int = Field(ge=1)  # reporting only (D-648)
    batch_units: int = Field(ge=1)
    #: stage 1's fixed exits per edge type (D-622), filled from s01_edge.yaml at load time
    exits: dict[str, EdgeTypeSpec] = Field(default_factory=dict)


def load_s03_config(path: Path | None = None, s01_path: Path | None = None) -> S03EntryConfig:
    target = path if path is not None else DEFAULT_PATH
    if not target.is_file():
        raise ConfigError("stage-3 config not found", config_path=target)
    try:
        data: dict[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if "exits" in data:
            raise ConfigError(
                "the stage-3 exits are stage 1's (D-622): remove 'exits' from the stage-3 config",
                config_path=target,
            )
        data["exits"] = load_s01_config(s01_path).edge_types
        return S03EntryConfig.model_validate(data)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read the stage-3 config: {exc}", config_path=target) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid stage-3 config: {exc}", config_path=target) from exc


#: operational settings that change no number (D-607) and so stay out of the hash and the ids
OPERATIONAL = frozenset({"batch_units"})


def stage_config_hash(cfg: S03EntryConfig) -> str:
    """sha256 of the stage config, the stage-1 exits included (D-805's pattern); operational
    settings left out (T13 N2)."""
    data = cfg.model_dump(mode="json", exclude=set(OPERATIONAL))
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()
