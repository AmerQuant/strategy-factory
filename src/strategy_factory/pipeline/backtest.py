"""One backtest: components + cost arrays + conversion + config -> engine -> ``RunResult``.

The glue between the typed layers and the pure engine (T08, F-0.3.1). The engine settings
(capital, notional, disaster-stop multiple, ATR length, futures contracts) come from
``configs/engine/default.yaml`` (CLAUDE.md rule 1, D-004, D-130, D-329).

Sizing mode (D-313, D-329, D-337): futures -> fixed contracts; ``tradingview`` intrabar mode
(parity) -> TradingView sizing; otherwise research sizing floored to the broker volume step
of the cost profile.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from strategy_factory.components.base import Bars, ExitSpec, ParamValue
from strategy_factory.components.indicators import atr as atr_indicator
from strategy_factory.components.registry import default_registry
from strategy_factory.core.errors import ConfigError
from strategy_factory.costs.arrays import STEP_REL_TOL, CostArrays
from strategy_factory.data.conversion import ConversionArrays
from strategy_factory.engine import kernel as k
from strategy_factory.engine.api import (
    CostInputs,
    ExitParams,
    MarketArrays,
    SimResult,
    SizingInputs,
    simulate,
)
from strategy_factory.metrics.containers import EquityCurve, RunMeta, RunResult, TradeLog

DEFAULT_ENGINE_CONFIG = Path("configs") / "engine" / "default.yaml"
Direction = Literal["long", "short"]
IntrabarMode = Literal["tradingview", "pessimistic"]
MODES: dict[str, int] = {"tradingview": k.MODE_TRADINGVIEW, "pessimistic": k.MODE_PESSIMISTIC}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EngineConfig(_Frozen):
    initial_capital: float = Field(gt=0)
    notional: float = Field(gt=0)
    disaster_stop_atr: float = Field(gt=0)
    atr_length: int = Field(ge=1)
    futures_contracts: float = Field(gt=0)


def load_engine_config(path: Path | None = None) -> EngineConfig:
    target = path if path is not None else DEFAULT_ENGINE_CONFIG
    try:
        return EngineConfig.model_validate(yaml.safe_load(target.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read engine config: {exc}", config_path=target) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid engine config: {exc}", config_path=target) from exc


class BacktestSpec(_Frozen):
    """What is simulated: one entry component (+ params) and the exit rules (first hit).

    The fixed disaster stop is not part of the spec (D-130): it comes from the engine config.
    """

    entry: str = Field(min_length=1)
    entry_params: dict[str, ParamValue] = Field(default_factory=dict)
    exit: ExitSpec = Field(default_factory=ExitSpec)

    def spec_hash(self) -> str:
        data = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FuturesSizing:
    """Futures (D-061): P&L = points x point value per contract; fixed count (D-329)."""

    point_value: float


def _ts_ns(ts_us: Any) -> np.ndarray:
    return (np.asarray(ts_us, dtype=np.int64) * 1000).astype("datetime64[ns]")


def market_arrays(bars: Mapping[str, Any], atr_length: int) -> MarketArrays:
    o, h, lo, c = (np.asarray(bars[x], dtype=np.float64) for x in ("open", "high", "low", "close"))
    return MarketArrays(o, h, lo, c, atr_indicator(h, lo, c, atr_length))


def cost_inputs(costs: CostArrays) -> CostInputs:
    return CostInputs(
        half_spread=costs.half_spread,
        slippage_fixed=costs.slippage_fixed,
        slippage_atr_frac=costs.slippage_atr_frac,
        swap_long=costs.swap_long_per_notional_day,
        swap_short=costs.swap_short_per_notional_day,
        rollover_mask=costs.rollover_mask,
        triple_mask=costs.triple_mask,
        commission_params=costs.commission_params,
        commission_in_quote=costs.commission_in_quote,
    )


def sizing_inputs(
    costs: CostArrays, cfg: EngineConfig, intrabar_mode: IntrabarMode, futures: FuturesSizing | None
) -> SizingInputs:
    if futures is not None:
        mode = k.SIZE_CONTRACTS
    elif intrabar_mode == "tradingview":
        mode = k.SIZE_PARITY
    else:
        mode = k.SIZE_RESEARCH
    return SizingInputs(
        mode=mode,
        notional=cfg.notional,
        initial_capital=cfg.initial_capital,
        contract_size=costs.contract_size,
        volume_step=costs.volume_step,
        min_volume=costs.min_volume,
        step_rel_tol=STEP_REL_TOL,
        contracts=cfg.futures_contracts,
        point_value=futures.point_value if futures is not None else 1.0,
    )


def exit_params(spec: ExitSpec, cfg: EngineConfig) -> ExitParams:
    nan = float("nan")
    return ExitParams(
        time_exit_bars=spec.time_exit_bars or 0,
        sl_atr=nan if spec.sl_atr is None else spec.sl_atr,
        tp_atr=nan if spec.tp_atr is None else spec.tp_atr,
        trail_atr=nan if spec.trail_atr is None else spec.trail_atr,
        disaster_atr=cfg.disaster_stop_atr,
    )


def entry_signals(bars: Mapping[str, Any], spec: BacktestSpec, direction: Direction) -> np.ndarray:
    comp = default_registry().get(spec.entry)
    b = Bars(*(np.asarray(bars[x], dtype=np.float64) for x in ("open", "high", "low", "close")))
    long_, short = comp.signals(b, spec.entry_params)
    return np.asarray(long_ if direction == "long" else short, dtype=np.bool_)


def to_run_result(
    sim: SimResult,
    ts_us: Any,
    direction: int,
    meta: RunMeta,
    cfg: EngineConfig,
) -> RunResult:
    ts = _ts_ns(ts_us)
    n_tr = sim.entry_idx.shape[0]
    trades = TradeLog(
        entry_idx=sim.entry_idx,
        exit_idx=sim.exit_idx,
        entry_ts=ts[sim.entry_idx],
        exit_ts=ts[sim.exit_idx],
        direction=np.full(n_tr, direction, dtype=np.int64),
        qty=sim.qty,
        entry_price=sim.entry_price,
        exit_price=sim.exit_price,
        pnl_gross=sim.pnl_gross,
        cost_spread=sim.cost_spread,
        cost_slippage=sim.cost_slippage,
        cost_commission=sim.cost_commission,
        cost_swap=sim.cost_swap,
        pnl_net=sim.pnl_net,
        exit_reason=sim.exit_reason,
        mae=sim.mae,
        mfe=sim.mfe,
        atr_at_entry=sim.atr_at_entry,
        bars_held=sim.exit_idx - sim.entry_idx,
    )
    equity = EquityCurve(
        ts=ts,
        equity_mtm=sim.equity,
        in_position=sim.in_position,
        realized_pnl=sim.realized_pnl,
        initial_capital=cfg.initial_capital,
        notional=cfg.notional,
        open_pnl_end=sim.open_pnl_end,
    )
    return RunResult(trades=trades, equity=equity, meta=meta)


def run_backtest(
    bars: Mapping[str, Any],
    spec: BacktestSpec,
    costs: CostArrays,
    *,
    symbol: str,
    timeframe: str,
    direction: Direction,
    intrabar_mode: IntrabarMode,
    exit_signal: Any = None,
    fx: ConversionArrays | None = None,
    futures: FuturesSizing | None = None,
    config: EngineConfig | None = None,
) -> RunResult:
    """Simulate ``spec`` on ``bars`` (``ts`` µs UTC bar-start, OHLC) and validate the result.

    ``exit_signal`` (bool per bar, evaluated at the close) is required when the exit spec uses
    ``signal_exit``. ``fx`` converts a non-USD quote currency (D-307, D-316, D-328); ``None``
    means USD.
    """
    cfg = config if config is not None else load_engine_config()
    n = int(np.asarray(bars["close"]).shape[0])
    if spec.exit.signal_exit and exit_signal is None:
        raise ConfigError("the exit spec uses signal_exit but no exit_signal was given")
    exit_sig = (
        np.zeros(n, dtype=np.bool_)
        if not spec.exit.signal_exit
        else np.asarray(exit_signal, dtype=np.bool_)
    )
    if fx is not None and fx.quote_ccy != costs.quote_ccy:
        raise ConfigError(f"conversion for {fx.quote_ccy}, profile quotes {costs.quote_ccy}")
    if fx is None and costs.quote_ccy != "USD":
        raise ConfigError(f"{symbol}: quote currency {costs.quote_ccy} needs conversion arrays")
    d = 1 if direction == "long" else -1
    sim = simulate(
        market_arrays(bars, cfg.atr_length),
        entry_signals(bars, spec, direction),
        exit_sig,
        d,
        exit_params(spec.exit, cfg),
        cost_inputs(costs),
        sizing_inputs(costs, cfg, intrabar_mode, futures),
        MODES[intrabar_mode],
        None if fx is None else fx.fx_open,
        None if fx is None else fx.fx_close,
    )
    meta = RunMeta(
        symbol=symbol,
        timeframe=timeframe,
        spec_hash=spec.spec_hash(),
        cost_status="placeholder" if costs.placeholder else "verified",
        intrabar_mode=intrabar_mode,
        stress=None if costs.stress == 1.0 else f"x{costs.stress:g}",
        n_skipped_min_volume=sim.n_skipped_min_volume,
        volume_step_assumed=costs.volume_step_assumed or futures is not None,  # D-314
        contracts_fixed=futures is not None,
        fx_peg=fx is not None and fx.peg,
    )
    return to_run_result(sim, bars["ts"], d, meta, cfg)
