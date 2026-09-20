"""Parity run configuration (T11 §2, D-348): the Pine settings a parity result depends on.

``configs/parity/<name>.yaml`` holds, per reference:

* ``reference`` -- the chart-data and trade-list file names under
  ``SFAC_RAW_ROOT/reference/tradingview/parity/``, plus the symbol and timeframe as exported;
* ``pine`` -- **every setting D-348 lists**: ATR length, initial capital, quantity type and
  value, commission, slippage, pyramiding, ``process_orders_on_close``, ``calc_on_every_tick``,
  the bar magnifier, the fill assumptions and the export timezone;
* ``engine`` -- ``parity_qty_step`` (required, D-347) and the Pine ``atr_length`` stated
  explicitly (D-343), as an :class:`~strategy_factory.core.config.EngineConfig`;
* ``strategy`` -- the ``BacktestSpec`` that reproduces the Pine strategy.

**A parity result is worthless if the settings it was produced under are unknown**, so every
``pine`` field is required: the model has no defaults there. The engine section is the same
model a pipeline config uses, so ``config_hash`` covers it (T10b).

**Costs come from the ``pine`` block only** (D-362): commission and slippage are built from it,
never from a Moneta profile, and the broker volume step and minimum never apply (D-347).
"""

from __future__ import annotations

import zoneinfo
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from strategy_factory.core.config import EngineConfig, canonical_json
from strategy_factory.core.errors import ConfigError

PARITY_DIR = Path("configs") / "parity"
QtyType = Literal["fixed_contracts", "percent_of_equity", "cash_amount"]
CommissionType = Literal["none", "percent", "per_contract", "per_order"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReferenceFiles(_Frozen):
    """The exported files, relative to ``SFAC_RAW_ROOT/reference/tradingview/parity/``."""

    chart_data: str = Field(min_length=1)
    trade_list: str | None = None  # arrives with the exports (D-360)
    symbol: str = Field(min_length=1)  # as TradingView names it, e.g. "BATS:SPY"
    timeframe: str = Field(min_length=1)  # as exported, e.g. "1D", "60"


class PineSettings(_Frozen):
    """The Strategy Properties of the Pine script (D-348). No defaults: all of it is required."""

    atr_length: int = Field(ge=1)  # D-343: the script's length, not the research default
    initial_capital: float = Field(gt=0)
    qty_type: QtyType
    qty_value: float = Field(gt=0)
    commission_type: CommissionType
    commission_value: float = Field(ge=0)
    slippage_ticks: int = Field(ge=0)
    tick_size: float = Field(gt=0)  # to turn slippage ticks into a price
    pyramiding: int = Field(ge=0)
    process_orders_on_close: bool
    calc_on_every_tick: bool
    bar_magnifier: bool
    fill_assumptions: str = Field(min_length=1)  # free text, recorded verbatim
    export_timezone: str = Field(min_length=1)  # IANA name of the chart's timezone

    @field_validator("export_timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        try:
            zoneinfo.ZoneInfo(value)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA time zone {value!r}") from exc
        return value

    @model_validator(mode="after")
    def _supported(self) -> PineSettings:
        if self.pyramiding != 0:
            raise ValueError("the engine holds one position per strategy (D-004): pyramiding 0")
        if self.commission_type != "none" and self.commission_value <= 0:
            raise ValueError("a commission type other than 'none' needs a positive value")
        return self

    def tz(self) -> zoneinfo.ZoneInfo:
        return zoneinfo.ZoneInfo(self.export_timezone)

    def slippage_price(self) -> float:
        """Slippage in price units, as TradingView applies it (ticks x tick size)."""
        return self.slippage_ticks * self.tick_size


class StrategyRef(_Frozen):
    """The registered entry component and the exit rules that reproduce the Pine strategy."""

    entry: str = Field(min_length=1)
    entry_params: dict[str, Any] = Field(default_factory=dict)
    direction: Literal["long", "short"] = "long"
    exit: dict[str, Any] = Field(default_factory=dict)  # ExitSpec fields
    note: str = ""


class ParityConfig(_Frozen):
    """One parity run: a reference, its Pine settings, the engine inputs and the strategy."""

    name: str = Field(min_length=1)
    reference: ReferenceFiles
    pine: PineSettings
    engine: EngineConfig
    strategy: StrategyRef | None = None  # filled once the Pine sources arrive (D-361)
    intrabar_mode: Literal["tradingview"] = "tradingview"
    # D-011 thresholds; here, never in code (CLAUDE.md rule 1)
    min_matched_share: float = Field(default=0.98, ge=0, le=1)
    max_net_profit_diff: float = Field(default=0.03, ge=0)

    @model_validator(mode="after")
    def _parity_inputs(self) -> ParityConfig:
        if self.engine.parity_qty_step is None:
            raise ValueError(
                "a parity run needs engine.parity_qty_step (D-347): the TradingView quantity "
                "step of the symbol, e.g. 1 for BATS:SPY, 0.01 for OANDA:XAUUSD"
            )
        if self.engine.atr_length != self.pine.atr_length:
            raise ValueError(
                f"engine.atr_length {self.engine.atr_length} must equal the Pine "
                f"atr_length {self.pine.atr_length} (D-343)"
            )
        if self.engine.initial_capital != self.pine.initial_capital:
            raise ValueError("engine.initial_capital must equal the Pine initial capital")
        if self.engine.parity_tick_size is None:
            raise ValueError(
                "a parity run needs engine.parity_tick_size (D-366): the symbol's mintick, "
                "which the Pine scripts divide the stop and target distances by"
            )
        if self.engine.parity_tick_size != self.pine.tick_size:
            raise ValueError(
                f"engine.parity_tick_size {self.engine.parity_tick_size} must equal the "
                f"symbol's tick size {self.pine.tick_size} (D-366)"
            )
        return self

    def canonical(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def content_hash(self) -> str:
        """sha256 of the canonical JSON -- what the run's ``config_hash`` binds (T10b)."""
        import hashlib

        return hashlib.sha256(canonical_json(self.canonical()).encode("utf-8")).hexdigest()


def load_parity_config(path: Path) -> ParityConfig:
    if not path.is_file():
        raise ConfigError("parity config not found", config_path=path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return ParityConfig.model_validate(data)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read parity config: {exc}", config_path=path) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid parity config: {exc}", config_path=path) from exc
