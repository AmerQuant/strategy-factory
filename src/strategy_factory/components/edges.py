"""Edge-type registry (F-0.4.3), read from ``configs/edges/edge_types.yaml``.

Edge types are configuration, not code (spec addendum §1.1): adding a type is a YAML change;
entry components only reference its ``id`` and, for stage-1 probes, one of its ``groups``.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from strategy_factory.core.errors import ConfigError

DEFAULT_EDGE_TYPES = Path("configs") / "edges" / "edge_types.yaml"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EdgeGroup(_Frozen):
    id: str
    name_fa: str = ""


class EdgeType(_Frozen):
    id: str
    name_fa: str = ""
    name_en: str = ""
    groups: tuple[EdgeGroup, ...] = ()

    @model_validator(mode="after")
    def _unique_groups(self) -> EdgeType:
        ids = [g.id for g in self.groups]
        if len(set(ids)) != len(ids):
            raise ValueError(f"edge type {self.id}: duplicate group ids {ids}")
        return self

    def group_ids(self) -> tuple[str, ...]:
        return tuple(g.id for g in self.groups)


class EdgeTypes(_Frozen):
    edge_types: tuple[EdgeType, ...]

    @model_validator(mode="after")
    def _unique_ids(self) -> EdgeTypes:
        ids = self.ids()
        if not ids:
            raise ValueError("at least one edge type is required")
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate edge type ids: {list(ids)}")
        return self

    def ids(self) -> tuple[str, ...]:
        return tuple(e.id for e in self.edge_types)

    def get(self, edge_id: str) -> EdgeType:
        for e in self.edge_types:
            if e.id == edge_id:
                return e
        raise ConfigError(f"unknown edge type {edge_id!r}; known: {list(self.ids())}")


def load_edge_types(path: Path | None = None) -> EdgeTypes:
    """Load and validate the edge-type registry (the file is required)."""
    target = path if path is not None else DEFAULT_EDGE_TYPES
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read edge-type registry: {exc}", config_path=target) from exc
    try:
        return EdgeTypes.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid edge-type registry: {exc}", config_path=target) from exc
