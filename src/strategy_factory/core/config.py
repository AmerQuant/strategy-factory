"""Pipeline configuration (F-0.8.2).

A pipeline YAML names the universe, symbols, timeframes, stages, gate file, intrabar mode,
seed and cost-stress multipliers. :func:`resolve_config` fills ``data_snapshots`` at run
start from the catalog references::

    data_snapshots: {SYMBOL: {TIMEFRAME: {source: ..., snapshot_hash: ...}}}

and that resolved config is what the registry stores. A run cannot start without resolved
snapshots (:func:`require_resolved`; the registry writer checks the key too).
``config_hash`` is the sha256 of the canonical JSON of the resolved config, independent of key
order.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from strategy_factory.core.errors import ConfigError

IntrabarMode = Literal["tradingview", "pessimistic"]


class SnapshotRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1)
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PipelineConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    universe: Path = Path("configs") / "universe.yaml"
    symbols: tuple[str, ...] = Field(min_length=1)
    timeframes: tuple[str, ...] = Field(min_length=1)
    stages: tuple[str, ...] = Field(min_length=1)
    gates: Path = Path("configs") / "gates" / "default.yaml"
    intrabar_mode: IntrabarMode = "pessimistic"
    seed: int = 42
    cost_stress: tuple[float, ...] = (1.5, 2.0, 3.0)
    data_snapshots: dict[str, dict[str, SnapshotRef]] = Field(default_factory=dict)

    @field_validator("symbols", "timeframes", "stages")
    @classmethod
    def _unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError(f"duplicate entries in {list(value)}")
        return value

    @field_validator("cost_stress")
    @classmethod
    def _stress(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(v < 1 for v in value):
            raise ValueError("cost_stress multipliers must be >= 1")
        return value

    @property
    def is_resolved(self) -> bool:
        return all(
            tf in self.data_snapshots.get(sym, {}) for sym in self.symbols for tf in self.timeframes
        )

    def canonical(self) -> dict[str, Any]:
        """JSON-ready dict (paths as POSIX strings) used for storage and hashing."""
        data = self.model_dump(mode="json")
        data["universe"] = self.universe.as_posix()
        data["gates"] = self.gates.as_posix()
        return data


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def config_hash(config: PipelineConfig | dict[str, Any]) -> str:
    data = config.canonical() if isinstance(config, PipelineConfig) else config
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def load_pipeline_config(path: Path) -> PipelineConfig:
    if not path.is_file():
        raise ConfigError("pipeline config not found", config_path=path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return PipelineConfig.model_validate(data)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read pipeline config: {exc}", config_path=path) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid pipeline config: {exc}", config_path=path) from exc


def validate_config(cfg: PipelineConfig, config_path: Path | None = None) -> None:
    """Symbols tradable in the universe, timeframes listed, stages and gates known."""
    from strategy_factory.core.universe import load_universe
    from strategy_factory.gates.engine import load_gate_config

    universe = load_universe(cfg.universe).by_symbol()
    gates = load_gate_config(cfg.gates)
    problems: list[str] = []
    for sym in cfg.symbols:
        entry = universe.get(sym)
        if entry is None:
            problems.append(f"{sym}: not in the universe")
            continue
        if not entry.tradable:
            problems.append(f"{sym}: not tradable ({entry.asset_class})")
        missing = [tf for tf in cfg.timeframes if tf not in entry.timeframes]
        if missing:
            problems.append(f"{sym}: timeframes {missing} not in the universe entry")
    unknown = [s for s in cfg.stages if s not in gates.stages]
    if unknown:
        problems.append(f"stages without gates: {unknown}")
    if problems:
        raise ConfigError(
            "pipeline config invalid: " + "; ".join(problems), config_path=config_path
        )


def resolve_config(
    cfg: PipelineConfig, catalog_root: Path | None = None, config_path: Path | None = None
) -> PipelineConfig:
    """``cfg`` with ``data_snapshots`` taken from the catalog references (all pairs required)."""
    from strategy_factory.core.universe import load_universe
    from strategy_factory.data.catalog import Catalog
    from strategy_factory.data.quality import ensure_usable

    validate_config(cfg, config_path)
    universe = load_universe(cfg.universe).by_symbol()
    cat = Catalog(catalog_root)
    snaps: dict[str, dict[str, SnapshotRef]] = {}
    missing: list[str] = []
    for sym in cfg.symbols:
        for tf in cfg.timeframes:
            if not cat.has_reference(sym, tf):
                missing.append(f"{sym} {tf}")
                continue
            meta = cat.get_reference(sym, tf)
            if meta.source != universe[sym].reference_source:
                raise ConfigError(
                    f"{sym} {tf}: reference snapshot from {meta.source!r}, universe declares "
                    f"{universe[sym].reference_source!r}",
                    config_path=config_path,
                )
            ensure_usable(cat, meta.key())
            snaps.setdefault(sym, {})[tf] = SnapshotRef(
                source=meta.source, snapshot_hash=meta.snapshot_hash or ""
            )
    if missing:
        raise ConfigError(
            "no reference snapshot in the catalog for: " + ", ".join(missing),
            config_path=config_path,
        )
    return cfg.model_copy(update={"data_snapshots": snaps})


def require_resolved(cfg: PipelineConfig) -> PipelineConfig:
    """Refuse a config whose data snapshots are not resolved (a run needs them)."""
    if not cfg.is_resolved:
        raise ConfigError(
            "pipeline config has unresolved data_snapshots; resolve it at run start "
            "(sfac config resolve) -- a run cannot start without its data snapshot hashes"
        )
    return cfg


def start_run(cfg: PipelineConfig, writer: Any, notes: str = "") -> Any:
    """Start a registry run with the resolved config (refuses an unresolved one)."""
    require_resolved(cfg)
    return writer.start_run(cfg.canonical(), seed=cfg.seed, notes=notes)
