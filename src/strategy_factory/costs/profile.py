"""Cost-profile schema, profile files and symbol assignments (F-0.2.1, F-0.2.2, F-0.2.3, F-0.2.4).

Conventions:

* **Spread values are full spreads** (ask - bid); the engine arrays carry half of them.
* Amounts are in ``price`` units, ``bps`` of the fill price, or ``pip`` (``pip_size``
  price units; the profile or a symbol override must define ``pip_size``).
* **Swap values are credits to the position**; a negative value is a charge.
  ``annual_rate`` is divided by ``day_count`` (Moneta: 360, D-320; default 365).
  ``points_per_day``: ``points x point_size`` price units per instrument unit per day.
  ``currency_per_lot_day``: quote-currency amount per lot per day (D-321). The engine turns
  every model into money on the mark-to-market notional of the rollover bar (D-312).
* Commission ``per_lot``: lots = quantity (instrument units, e.g. EUR for EURUSD) /
  ``lot_size``; the amount is charged per side. ``per_order``: a fixed amount per side
  (D-319). Every commission model has a ``currency`` (USD by default); the engine converts
  it only when it is the quote currency (D-328).
* Spread ``broker_scaled`` (D-523, F-0.2.2): the hourly shape of the snapshot spread, scaled
  so its bar-weighted mean over the **development** bars equals ``broker_spread`` (D-340).
* Instrument fields (D-313, D-314, D-315): ``contract_size`` (instrument units per lot),
  ``volume_step`` and ``min_volume`` in **lots**. A profile that does not set them gets the
  D-314 assumption (1 unit per lot, step 1, minimum 1) with ``volume_step_assumed``.

Files: every ``configs/costs/*.yaml`` except ``assignments.yaml`` holds one profile;
``assignments.yaml`` maps asset classes (groups) and symbols to profiles, with optional
per-symbol overrides. The generated Moneta files (T06b) add ``moneta/moneta_profiles.yaml``
(a list under ``profiles``) and ``moneta/assignments.yaml`` (symbol entries); a symbol listed
in both assignment files is an error. **An unassigned symbol is an error: costs are
mandatory.**
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
MONETA_DIR = "moneta"
MONETA_PROFILES_FILE = "moneta_profiles.yaml"


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


class SpreadBrokerScaled(_Frozen):
    """Hourly median shape of the snapshot spread scaled to the broker's reference spread.

    ``broker_spread`` is the broker's full spread in price units. The scale factor is fitted
    so the bar-weighted mean of the hourly table over the development bars equals it; hours
    without data, or a snapshot without a spread column, use ``broker_spread`` itself.
    """

    mode: Literal["broker_scaled"] = "broker_scaled"
    broker_spread: float = Field(gt=0)


Spread = Annotated[
    SpreadFixed | SpreadHourly | SpreadFromData | SpreadBrokerScaled,
    Field(discriminator="mode"),
]


# -- commission --------------------------------------------------------------------------
class _Commission(_Frozen):
    currency: str = Field(default="USD", min_length=3, max_length=3)


class CommissionNone(_Commission):
    model: Literal["none"] = "none"


class CommissionPercent(_Commission):
    model: Literal["percent"] = "percent"
    rate: float = Field(ge=0)  # fraction of the traded value, per side


class CommissionPerShare(_Commission):
    model: Literal["per_share"] = "per_share"
    per_share: float = Field(ge=0)
    min_per_order: float = Field(default=0.0, ge=0)
    max_per_order: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _bounds(self) -> CommissionPerShare:
        if self.max_per_order is not None and self.max_per_order < self.min_per_order:
            raise ValueError("max_per_order must be >= min_per_order")
        return self


class CommissionPerLot(_Commission):
    model: Literal["per_lot"] = "per_lot"
    lot_size: float = Field(gt=0)  # instrument units per lot
    per_lot_per_side: float = Field(ge=0)


class CommissionPerOrder(_Commission):
    """A fixed amount per order, i.e. per side (D-319)."""

    model: Literal["per_order"] = "per_order"
    amount: float = Field(ge=0)


Commission = Annotated[
    CommissionNone | CommissionPercent | CommissionPerShare | CommissionPerLot | CommissionPerOrder,
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
    long: float  # points per instrument unit per day; negative = charge
    short: float
    point_size: float = Field(default=1.0, gt=0)  # price units per point (1.0 = price units)


class SwapCurrencyPerLot(RolloverRules):
    """Quote-currency amount per lot per day (Moneta ``in currency``, D-321)."""

    model: Literal["currency_per_lot_day"] = "currency_per_lot_day"
    long: float
    short: float


Swap = Annotated[
    SwapNone | SwapAnnualRate | SwapPoints | SwapCurrencyPerLot, Field(discriminator="model")
]


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
    # instrument (D-307, D-313 ... D-315); defaults = the D-314 assumption
    broker_symbol: str | None = None
    quote_ccy: str = Field(default="USD", min_length=3, max_length=3)
    point_value: float | None = Field(default=None, gt=0)  # money per point per lot (quote ccy)
    contract_size: float = Field(default=1.0, gt=0)  # instrument units per lot
    volume_step: float = Field(default=1.0, gt=0)  # lots
    min_volume: float = Field(default=1.0, gt=0)  # lots
    volume_step_assumed: bool = True
    to_verify: tuple[str, ...] = ()

    @property
    def is_placeholder(self) -> bool:
        return self.status == "placeholder"

    @model_validator(mode="after")
    def _checks(self) -> CostProfile:
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
        if self.min_volume < self.volume_step * (1.0 - 1e-9):
            raise ValueError(f"profile {self.name!r}: min_volume below volume_step")
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
        loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=loader) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read config: {exc}", config_path=path) from exc
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping", config_path=path)
    return data


def _add(profiles: dict[str, CostProfile], data: Any, path: Path) -> None:
    try:
        prof = CostProfile.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid cost profile: {exc}", config_path=path) from exc
    if prof.name in profiles:
        raise ConfigError(f"duplicate cost profile name {prof.name!r}", config_path=path)
    profiles[prof.name] = prof


def load_profiles(costs_dir: Path) -> dict[str, CostProfile]:
    """Every profile file in ``costs_dir`` plus the generated Moneta profiles, if present."""
    profiles: dict[str, CostProfile] = {}
    for path in sorted(costs_dir.glob("*.yaml")):
        if path.name == ASSIGNMENTS_FILE:
            continue
        _add(profiles, _read_yaml(path), path)
    generated = costs_dir / MONETA_DIR / MONETA_PROFILES_FILE
    if generated.is_file():
        items = _read_yaml(generated).get("profiles") or []
        if not isinstance(items, list):
            raise ConfigError("'profiles' must be a list", config_path=generated)
        for item in items:
            _add(profiles, item, generated)
    return profiles


def _assignments(path: Path) -> Assignments:
    try:
        return Assignments.model_validate(_read_yaml(path))
    except ValidationError as exc:
        raise ConfigError(f"invalid cost assignments: {exc}", config_path=path) from exc


def load_assignments(costs_dir: Path) -> Assignments:
    """``assignments.yaml`` merged with the generated ``moneta/assignments.yaml``."""
    path = costs_dir / ASSIGNMENTS_FILE
    if not path.is_file():
        raise ConfigError("cost assignments not found (costs are mandatory)", config_path=path)
    base = _assignments(path)
    generated = costs_dir / MONETA_DIR / ASSIGNMENTS_FILE
    if not generated.is_file():
        return base
    extra = _assignments(generated)
    if extra.groups:
        raise ConfigError("generated assignments may not define groups", config_path=generated)
    both = sorted(set(base.symbols) & set(extra.symbols))
    if both:
        raise ConfigError(
            f"symbols assigned in both assignment files: {both[:10]}", config_path=generated
        )
    return base.model_copy(update={"symbols": {**base.symbols, **extra.symbols}})


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
