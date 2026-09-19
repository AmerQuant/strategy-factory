"""Cost-profile schema, profile files and symbol assignments (F-0.2.1, F-0.2.3, F-0.2.4).

Conventions:

* **Spread values are full spreads** (ask - bid); the engine arrays carry half of them.
* Amounts are in ``price`` units, ``bps`` of the fill price, or ``pip`` (``pip_size``
  price units; the profile or a symbol override must define ``pip_size``).
* **Swap values are credits to the position** per unit of notional per day; a negative
  value is a charge. ``annual_rate`` is divided by ``day_count``.
* Commission ``per_lot``: lots = quantity (instrument units, e.g. EUR for EURUSD) /
  ``lot_size``; the amount is charged per side.

Files: every ``configs/costs/*.yaml`` except ``assignments.yaml`` holds one profile;
``assignments.yaml`` maps asset classes (groups) and symbols to profiles, with optional
per-symbol overrides. **An unassigned symbol is an error: costs are mandatory.**
"""

from __future__ import annotations

import csv
import datetime as dt
import zoneinfo
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from strategy_factory.core.errors import ConfigError

Unit = Literal["price", "bps", "pip"]
Weekday = Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
WEEKDAY_NUMBER: dict[str, int] = {
    "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6, "SUN": 7,
}  # fmt: skip
ASSIGNMENTS_FILE = "assignments.yaml"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Amount(_Frozen):
    value: float = Field(ge=0)
    unit: Unit = "price"


# -- spread ------------------------------------------------------------------------------
class SpreadFixed(_Frozen):
    mode: Literal["fixed"] = "fixed"
    fixed: Amount


class SpreadHourly(_Frozen):
    """24 full-spread values, index = UTC hour of the bar start."""

    mode: Literal["hourly_profile"] = "hourly_profile"
    hourly: tuple[float, ...]
    unit: Unit = "price"

    @field_validator("hourly")
    @classmethod
    def _24(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if len(value) != 24 or any(v < 0 for v in value):
            raise ValueError("hourly_profile needs 24 non-negative values (UTC hours 0..23)")
        return value


class SpreadFromData(_Frozen):
    """Median snapshot ``spread`` per UTC hour (development segment only) x ``scale``."""

    mode: Literal["from_data"] = "from_data"
    scale: float = Field(default=1.0, gt=0)
    fallback: Amount | None = None  # used for hours without data

    @field_validator("fallback")
    @classmethod
    def _no_bps(cls, value: Amount | None) -> Amount | None:
        if value is not None and value.unit == "bps":
            raise ValueError("from_data fallback must be in price units or pips")
        return value


Spread = Annotated[SpreadFixed | SpreadHourly | SpreadFromData, Field(discriminator="mode")]


# -- commission --------------------------------------------------------------------------
class CommissionNone(_Frozen):
    model: Literal["none"] = "none"


class CommissionPercent(_Frozen):
    model: Literal["percent"] = "percent"
    rate: float = Field(ge=0)  # fraction of the traded value, per side


class CommissionPerShare(_Frozen):
    model: Literal["per_share"] = "per_share"
    per_share: float = Field(ge=0)
    min_per_order: float = Field(default=0.0, ge=0)
    max_per_order: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _bounds(self) -> CommissionPerShare:
        if self.max_per_order is not None and self.max_per_order < self.min_per_order:
            raise ValueError("max_per_order must be >= min_per_order")
        return self


class CommissionPerLot(_Frozen):
    model: Literal["per_lot"] = "per_lot"
    lot_size: float = Field(gt=0)  # instrument units per lot
    per_lot_per_side: float = Field(ge=0)


Commission = Annotated[
    CommissionNone | CommissionPercent | CommissionPerShare | CommissionPerLot,
    Field(discriminator="model"),
]


# -- swap --------------------------------------------------------------------------------
class RolloverRules(_Frozen):
    rollover_time_local: str = "17:00"
    rollover_tz: str = "America/New_York"
    rollover_weekdays: tuple[Weekday, ...] = ("MON", "TUE", "WED", "THU", "FRI")
    triple_weekday: Weekday = "WED"

    @field_validator("rollover_time_local")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        try:
            dt.time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"expected HH:MM, got {value!r}") from exc
        return value

    @field_validator("rollover_tz")
    @classmethod
    def _tz(cls, value: str) -> str:
        try:
            zoneinfo.ZoneInfo(value)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA time zone {value!r}") from exc
        return value

    @model_validator(mode="after")
    def _triple_is_a_rollover_day(self) -> RolloverRules:
        if self.triple_weekday not in self.rollover_weekdays:
            raise ValueError("triple_weekday must be one of rollover_weekdays")
        return self


class SwapNone(_Frozen):
    model: Literal["none"] = "none"


class SwapAnnualRate(RolloverRules):
    model: Literal["annual_rate"] = "annual_rate"
    long: float  # annual rate on notional; negative = charge
    short: float
    day_count: int = Field(default=365, gt=0)


class SwapPoints(RolloverRules):
    model: Literal["points_per_day"] = "points_per_day"
    long: float  # price points per instrument unit per day; negative = charge
    short: float


Swap = Annotated[SwapNone | SwapAnnualRate | SwapPoints, Field(discriminator="model")]


class Slippage(_Frozen):
    fixed: Amount = Field(default_factory=lambda: Amount(value=0.0))
    atr_fraction: float = Field(default=0.0, ge=0)  # x ATR of the signal bar


class CostProfile(_Frozen):
    name: str = Field(min_length=1)
    status: Literal["placeholder", "verified"]
    source_note: str = ""
    pip_size: float | None = Field(default=None, gt=0)
    spread: Spread
    commission: Commission
    swap: Swap
    slippage: Slippage = Field(default_factory=Slippage)

    @property
    def is_placeholder(self) -> bool:
        return self.status == "placeholder"

    @model_validator(mode="after")
    def _pips_need_pip_size(self) -> CostProfile:
        amounts: list[Amount] = [self.slippage.fixed]
        if isinstance(self.spread, SpreadFixed):
            amounts.append(self.spread.fixed)
        if isinstance(self.spread, SpreadFromData) and self.spread.fallback is not None:
            amounts.append(self.spread.fallback)
        uses_pip = any(a.unit == "pip" and a.value > 0 for a in amounts) or (
            isinstance(self.spread, SpreadHourly) and self.spread.unit == "pip"
        )
        if uses_pip and self.pip_size is None:
            raise ValueError(f"profile {self.name!r} uses pips but defines no pip_size")
        return self


# -- assignments -------------------------------------------------------------------------
class SymbolAssignment(_Frozen):
    profile: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class Assignments(_Frozen):
    groups: dict[str, str] = Field(default_factory=dict)  # asset_class -> profile
    symbols: dict[str, SymbolAssignment] = Field(default_factory=dict)
    stress_multipliers: tuple[float, ...] = (1.5, 2.0, 3.0)

    @field_validator("stress_multipliers")
    @classmethod
    def _stress(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(v < 1.0 for v in value):
            raise ValueError("stress multipliers must be >= 1")
        return value


class CostsConfig(_Frozen):
    """Where profiles, assignments and the tradable universe live."""

    costs_dir: Path = Path("configs") / "costs"
    universe_files: tuple[Path, ...] = (
        Path("configs") / "universe" / "us_equity_daily.csv",
        Path("configs") / "universe" / "us_equity_hourly.csv",
        Path("configs") / "universe" / "dukascopy.csv",
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read config: {exc}", config_path=path) from exc
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping", config_path=path)
    return data


def load_profiles(costs_dir: Path) -> dict[str, CostProfile]:
    """Every profile file in ``costs_dir`` (all ``*.yaml`` except the assignments)."""
    profiles: dict[str, CostProfile] = {}
    for path in sorted(costs_dir.glob("*.yaml")):
        if path.name == ASSIGNMENTS_FILE:
            continue
        try:
            prof = CostProfile.model_validate(_read_yaml(path))
        except ValidationError as exc:
            raise ConfigError(f"invalid cost profile: {exc}", config_path=path) from exc
        if prof.name in profiles:
            raise ConfigError(f"duplicate cost profile name {prof.name!r}", config_path=path)
        profiles[prof.name] = prof
    return profiles


def load_assignments(costs_dir: Path) -> Assignments:
    path = costs_dir / ASSIGNMENTS_FILE
    if not path.is_file():
        raise ConfigError("cost assignments not found (costs are mandatory)", config_path=path)
    try:
        return Assignments.model_validate(_read_yaml(path))
    except ValidationError as exc:
        raise ConfigError(f"invalid cost assignments: {exc}", config_path=path) from exc


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def resolve_profile(
    symbol: str,
    asset_class: str,
    profiles: dict[str, CostProfile],
    assignments: Assignments,
    costs_dir: Path | None = None,
) -> CostProfile:
    """The cost profile of ``symbol``: symbol entry first, then its asset-class group."""
    where = (costs_dir / ASSIGNMENTS_FILE) if costs_dir else None
    entry = assignments.symbols.get(symbol)
    name = entry.profile if entry else assignments.groups.get(asset_class)
    if name is None:
        raise ConfigError(
            f"no cost profile assigned to {symbol} ({asset_class}); costs are mandatory",
            symbol=symbol,
            config_path=where,
        )
    if name not in profiles:
        raise ConfigError(f"unknown cost profile {name!r}", symbol=symbol, config_path=where)
    prof = profiles[name]
    if entry and entry.overrides:
        data = _merge(prof.model_dump(), entry.overrides)
        note = f"{prof.source_note} [overrides for {symbol}: {entry.overrides}]".strip()
        data["source_note"] = note
        try:
            prof = CostProfile.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(
                f"invalid overrides for {symbol}: {exc}", symbol=symbol, config_path=where
            ) from exc
    return prof


def universe_symbols(cfg: CostsConfig) -> dict[str, str]:
    """Tradable universe: symbol -> asset class (US equity lists + Dukascopy list)."""
    out: dict[str, str] = {}
    for path in cfg.universe_files:
        if not path.is_file():
            raise ConfigError("universe file not found", config_path=path)
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                out[row["symbol"]] = row.get("asset_class") or "us_equity"
    return out


def validate_all(cfg: CostsConfig) -> tuple[dict[str, str], list[str]]:
    """(symbol -> profile name, unassigned symbols); raises on invalid profiles/overrides."""
    profiles = load_profiles(cfg.costs_dir)
    assignments = load_assignments(cfg.costs_dir)
    for name in {*assignments.groups.values(), *(a.profile for a in assignments.symbols.values())}:
        if name not in profiles:
            raise ConfigError(
                f"assignment refers to unknown profile {name!r}",
                config_path=cfg.costs_dir / ASSIGNMENTS_FILE,
            )
    assigned: dict[str, str] = {}
    missing: list[str] = []
    for sym, cls in sorted(universe_symbols(cfg).items()):
        try:
            assigned[sym] = resolve_profile(sym, cls, profiles, assignments, cfg.costs_dir).name
        except ConfigError as exc:
            if "no cost profile" not in exc.message:
                raise
            missing.append(sym)
    return assigned, missing
