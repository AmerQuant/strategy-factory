"""Pipeline configuration (F-0.8.2).

A pipeline YAML names the universe, symbols, timeframes, stages, gate file, intrabar mode,
seed, cost-stress multipliers and the **engine settings**. :func:`resolve_config` fills
``data_snapshots`` and ``cost_inputs`` at run start from the catalog and the cost configs::

    data_snapshots: {SYMBOL: {TIMEFRAME: {source: ..., snapshot_hash: ...}}}
    cost_inputs:    {profile_names, profiles, moneta_spec_sha256, fx_conversion,
                     conversion_snapshots}

and that resolved config is what the registry stores. A run cannot start without resolved
snapshots (:func:`require_resolved`; the registry writer checks the key too).
``config_hash`` is the sha256 of the canonical JSON of the resolved config, independent of key
order.

**What the run hash covers (CLAUDE.md rule 8, T10b).** ``BacktestSpec.spec_hash`` (T08)
covers the strategy spec only, so the run config closes the rest of the gap:

* the ``engine`` section (:class:`EngineConfig`): capital, notional, disaster-stop multiple,
  ATR length (D-343), futures contracts and ``parity_qty_step`` (D-347);
* ``intrabar_mode`` (D-002);
* the data snapshot hashes;
* the **cost inputs** (:class:`CostInputsRef`): the content hash of every symbol's resolved
  cost profile, the SHA-256 of the broker spec behind the Moneta profiles (D-340), the FX
  conversion config (pairs and pegs, D-307) and the snapshot hashes of the conversion pairs
  the run needs (D-316).

``code_version`` is **stored, not hashed** (``registry.writer.code_version``): a dirty
working tree does not change the config.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from strategy_factory.core.errors import ConfigError

IntrabarMode = Literal["tradingview", "pessimistic"]
UniverseFilter = Literal["broker", "all"]
DEFAULT_ENGINE_CONFIG = Path("configs") / "engine" / "default.yaml"


class SnapshotRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1)
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class EngineConfig(BaseModel):
    """Engine run settings (T08, ``configs/engine/default.yaml``).

    The defaults live here (CLAUDE.md rule 1) and are restated in the YAML with their
    decision ids. Every field decides a result, so the whole model is part of the run
    ``config_hash`` as ``PipelineConfig.engine``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    initial_capital: float = Field(default=100_000.0, gt=0)  # D-004
    notional: float = Field(default=100_000.0, gt=0)  # D-004
    disaster_stop_atr: float = Field(default=3.0, gt=0)  # D-130: fixed, never optimized
    atr_length: int = Field(default=14, ge=1)  # D-343; parity runs pass the Pine length
    futures_contracts: float = Field(default=1.0, gt=0)  # D-329
    # parity section (D-347): the TradingView quantity step of the symbol; no default, a
    # parity run must set it (with the Pine ATR length, D-343)
    parity_qty_step: float | None = Field(default=None, gt=0)
    # D-366: the symbol's mintick. In parity mode stop and target distances are rounded to
    # whole ticks and measured from the fill, as Pine's math.round(k * atr / mintick) does.
    # None = the research behaviour (unrounded levels from the raw open).
    parity_tick_size: float | None = Field(default=None, gt=0)
    # D-367: mirror Pine's `strategy.position_size == 0` entry gate, which refuses a re-entry
    # on the close that schedules the exit. False = D-336, the research default.
    entry_requires_flat_at_signal: bool = False


def load_engine_config(path: Path | None = None) -> EngineConfig:
    target = path if path is not None else DEFAULT_ENGINE_CONFIG
    try:
        return EngineConfig.model_validate(yaml.safe_load(target.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read engine config: {exc}", config_path=target) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid engine config: {exc}", config_path=target) from exc


class CostInputsRef(BaseModel):
    """Everything the costs of a run depend on (T10b); filled by :func:`resolve_config`.

    ``profiles`` maps each traded symbol to the content hash of its **resolved** cost profile
    (:func:`strategy_factory.costs.profile.profile_content_hash`), so regenerating a profile
    with a different spread changes the run hash. ``moneta_spec_sha256`` is the SHA-256 of the
    broker xlsx those profiles were built from (D-340). ``fx_conversion`` is the content of
    ``configs/data/fx_conversion.yaml`` (pairs and pegs, D-307), and
    ``conversion_snapshots`` carries the snapshot hashes of the conversion pairs this run
    needs, in the same shape as ``data_snapshots`` (D-316).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_names: dict[str, str] = Field(default_factory=dict)
    profiles: dict[str, str] = Field(default_factory=dict)
    moneta_spec_sha256: str | None = None
    fx_conversion: dict[str, Any] = Field(default_factory=dict)
    conversion_snapshots: dict[str, dict[str, SnapshotRef]] = Field(default_factory=dict)


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
    # D-524: the default candidate universe is broker-tradable symbols only; with "all",
    # symbols without a broker symbol are allowed and listed in report_only at resolution.
    universe_filter: UniverseFilter = "broker"
    report_only: tuple[str, ...] = ()
    # T08 engine settings; part of config_hash (D-343, D-344, D-347)
    engine: EngineConfig = Field(default_factory=EngineConfig)
    data_snapshots: dict[str, dict[str, SnapshotRef]] = Field(default_factory=dict)
    cost_inputs: CostInputsRef | None = None

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


#: One message for the missing parity step, shared by the config validation and
#: ``pipeline.backtest.run_backtest`` so both refuse a parity run the same way (D-347).
PARITY_STEP_REQUIRED = (
    "parity (tradingview) runs need parity_qty_step in the engine config (D-347): the "
    "TradingView quantity step of the symbol, e.g. 1 for BATS:SPY, 0.01 for OANDA:XAUUSD"
)
#: D-343: a parity run reproduces a Pine script, so its ATR length is the script's, never the
#: research default. The config must state it, even when it happens to equal the default.
PARITY_ATR_LENGTH_REQUIRED = (
    "parity (tradingview) runs must set engine.atr_length explicitly (D-343): it is the ATR "
    "length of the Pine script being reproduced, not the research default"
)


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
        if cfg.universe_filter == "broker" and entry.tradable and entry.broker_symbol is None:
            problems.append(
                f"{sym}: not tradable at the broker (universe_filter: broker, D-524); "
                "use universe_filter: all for report-only research"
            )
    unknown = [s for s in cfg.stages if s not in gates.stages]
    if unknown:
        problems.append(f"stages without gates: {unknown}")
    if cfg.intrabar_mode == "tradingview":
        if cfg.engine.parity_qty_step is None:
            problems.append(PARITY_STEP_REQUIRED)
        if "atr_length" not in cfg.engine.model_fields_set:
            problems.append(PARITY_ATR_LENGTH_REQUIRED)
    if problems:
        raise ConfigError(
            "pipeline config invalid: " + "; ".join(problems), config_path=config_path
        )


def cost_profile_hashes(
    cfg: PipelineConfig,
    universe: Mapping[str, Any],
    costs_dir: Path | None = None,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """``(profile names, content hashes, quote currencies)`` per traded symbol (T10b)."""
    from strategy_factory.costs.profile import (
        load_assignments,
        load_profiles,
        profile_content_hash,
        resolve_profile,
    )

    cdir = costs_dir if costs_dir is not None else Path("configs") / "costs"
    profiles = load_profiles(cdir)
    assignments = load_assignments(cdir)
    names: dict[str, str] = {}
    hashes: dict[str, str] = {}
    quote: dict[str, str] = {}
    for sym in cfg.symbols:
        prof = resolve_profile(sym, universe[sym].asset_class, profiles, assignments, cdir)
        names[sym] = prof.name
        hashes[sym] = profile_content_hash(prof)
        quote[sym] = prof.quote_ccy
    return names, hashes, quote


def conversion_pairs_for(
    quote_ccy: Mapping[str, str], fx_path: Path | None = None
) -> tuple[list[str], Any]:
    """``(sorted conversion pairs the symbols need, the FX config)`` (D-307, D-316)."""
    from strategy_factory.data.conversion import load_fx_config

    fx = load_fx_config(fx_path)
    pairs: set[str] = set()
    for sym, ccy in sorted(quote_ccy.items()):
        if ccy == "USD" or ccy in fx.pegs:
            continue
        rule = fx.pair_for(ccy)
        if rule is None:
            raise ConfigError(
                f"{sym}: no conversion rule for quote currency {ccy} (D-307)", symbol=sym
            )
        pairs.add(rule.pair)
    return sorted(pairs), fx


def resolve_config(
    cfg: PipelineConfig,
    catalog_root: Path | None = None,
    config_path: Path | None = None,
    costs_dir: Path | None = None,
    fx_config_path: Path | None = None,
) -> PipelineConfig:
    """``cfg`` with ``data_snapshots`` and ``cost_inputs`` resolved (all of them required)."""
    from strategy_factory.core.universe import load_universe
    from strategy_factory.costs.profile import moneta_profile_names, moneta_spec_sha256
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
    # -- cost inputs (T10b): profiles, broker spec, FX config, conversion snapshots --------
    cdir = costs_dir if costs_dir is not None else Path("configs") / "costs"
    names, hashes, quote = cost_profile_hashes(cfg, universe, cdir)
    pairs, fx = conversion_pairs_for(quote, fx_config_path)
    conv: dict[str, dict[str, SnapshotRef]] = {}
    missing_pairs: list[str] = []
    for pair in pairs:
        for tf in cfg.timeframes:
            if not cat.has_reference(pair, tf):
                missing_pairs.append(f"{pair} {tf}")
                continue
            meta = cat.get_reference(pair, tf)
            ensure_usable(cat, meta.key())
            conv.setdefault(pair, {})[tf] = SnapshotRef(
                source=meta.source, snapshot_hash=meta.snapshot_hash or ""
            )
    if missing_pairs:
        raise ConfigError(
            "no reference snapshot for the conversion pair(s) the run needs (D-316): "
            + ", ".join(missing_pairs),
            config_path=config_path,
        )
    generated = moneta_profile_names(cdir)
    cost_inputs = CostInputsRef(
        profile_names=names,
        profiles=hashes,
        moneta_spec_sha256=(
            moneta_spec_sha256(cdir) if generated & set(names.values()) else None  # D-340
        ),
        fx_conversion=fx.model_dump(mode="json"),
        conversion_snapshots=conv,
    )
    report_only = tuple(s for s in cfg.symbols if universe[s].broker_symbol is None)
    return cfg.model_copy(
        update={
            "data_snapshots": snaps,
            "report_only": report_only,
            "cost_inputs": cost_inputs,
        }
    )


def check_cost_inputs(
    stored: Mapping[str, Any],
    costs_dir: Path | None = None,
    fx_config_path: Path | None = None,
) -> list[str]:
    """Differences between a **stored** run config's cost inputs and today's configs (T10b).

    Used by ``sfac reproduce``: an empty list means the costs of the stored run can be
    rebuilt from the current configs. A non-empty list means the run cannot be reproduced,
    and every entry names what changed (symbol, stored hash, current hash).
    """
    recorded = stored.get("cost_inputs")
    if not isinstance(recorded, Mapping):
        return ["cost_inputs are not recorded in the run config (the run predates T10b)"]
    cfg = PipelineConfig.model_validate(dict(stored))
    from strategy_factory.core.universe import load_universe
    from strategy_factory.costs.profile import moneta_profile_names, moneta_spec_sha256

    cdir = costs_dir if costs_dir is not None else Path("configs") / "costs"
    universe = load_universe(cfg.universe).by_symbol()
    problems: list[str] = []
    try:
        names, hashes, quote = cost_profile_hashes(cfg, universe, cdir)
        _, fx = conversion_pairs_for(quote, fx_config_path)
    except ConfigError as exc:
        return [f"cost profiles cannot be resolved today: {exc}"]
    old_names = dict(recorded.get("profile_names") or {})
    old_hashes = dict(recorded.get("profiles") or {})
    for sym in sorted(set(old_hashes) | set(hashes)):
        was, now = old_hashes.get(sym), hashes.get(sym)
        if was == now:
            continue
        problems.append(
            f"{sym}: cost profile changed -- run used {old_names.get(sym, '?')} "
            f"{(was or 'none')[:12]}, configs give {names.get(sym, '?')} {(now or 'none')[:12]}"
        )
    generated = moneta_profile_names(cdir)
    now_sha = moneta_spec_sha256(cdir) if generated & set(names.values()) else None
    if recorded.get("moneta_spec_sha256") != now_sha:
        problems.append(
            f"Moneta broker spec changed (D-340): run used "
            f"{str(recorded.get('moneta_spec_sha256'))[:12]}, configs give {str(now_sha)[:12]}"
        )
    if dict(recorded.get("fx_conversion") or {}) != fx.model_dump(mode="json"):
        problems.append("configs/data/fx_conversion.yaml changed (pairs or pegs, D-307)")
    was_pairs = set(recorded.get("conversion_snapshots") or {})
    now_pairs = set(conversion_pairs_for(quote, fx_config_path)[0])
    if was_pairs != now_pairs:
        problems.append(
            f"the conversion pairs the run needs changed (D-316): run used "
            f"{sorted(was_pairs) or 'none'}, configs give {sorted(now_pairs) or 'none'}"
        )
    return problems


def require_resolved(cfg: PipelineConfig) -> PipelineConfig:
    """Refuse a config whose data snapshots or cost inputs are not resolved (a run needs both)."""
    if not cfg.is_resolved:
        raise ConfigError(
            "pipeline config has unresolved data_snapshots; resolve it at run start "
            "(sfac config resolve) -- a run cannot start without its data snapshot hashes"
        )
    if cfg.cost_inputs is None or set(cfg.cost_inputs.profiles) != set(cfg.symbols):
        raise ConfigError(
            "pipeline config has unresolved cost_inputs; resolve it at run start "
            "(sfac config resolve) -- costs are mandatory (CLAUDE.md rule 4) and a run that "
            "does not record them cannot be reproduced"
        )
    return cfg


def start_run(cfg: PipelineConfig, writer: Any, notes: str = "") -> Any:
    """Start a registry run with the resolved config (refuses an unresolved one)."""
    require_resolved(cfg)
    return writer.start_run(cfg.canonical(), seed=cfg.seed, notes=notes)
