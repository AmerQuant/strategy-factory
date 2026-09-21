"""Run one parity reference end to end: config + fixtures -> engine -> comparison (T11 §3/§4).

This is the glue the D-011 gate needs. It is **parity only**: it reads the committed reference
fixtures (D-359), builds the run from the parity config alone, and never touches a Moneta cost
profile, a snapshot or the registry.

The exit rules of the two Pine scripts map onto :class:`ExitSpec` fields, except the MR
script's ``close > high[1]``, which is a *signal* exit. No exit component exists yet, so
``BacktestSpec`` takes that signal as an array (D-344, the interim contract) and the rule is
named in the parity config and implemented in :data:`PARITY_EXIT_RULES` here (**D-370**). This
adds no entry component and no research behaviour: the table is reachable only from a parity
config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from strategy_factory.components.base import ExitSpec
from strategy_factory.core.errors import ConfigError
from strategy_factory.core.parity_config import ParityConfig, StrategyRef
from strategy_factory.costs.parity import parity_cost_arrays
from strategy_factory.pipeline.backtest import BacktestSpec, run_backtest
from strategy_factory.selftest.parity_compare import Comparison, compare
from strategy_factory.selftest.parity_refs import (
    ChartData,
    TradeList,
    fixture,
    load_chart_data,
    load_manifest,
    load_strategy_report,
    load_trade_list,
)
from strategy_factory.selftest.parity_report import Verdict, verdict

if TYPE_CHECKING:  # pragma: no cover - typing only
    from strategy_factory.metrics.containers import RunResult

__all__ = [
    "PARITY_EXIT_RULES",
    "ParityRun",
    "backtest_spec",
    "exit_signal_array",
    "run_reference",
]


def _close_above_previous_high(chart: ChartData) -> np.ndarray:
    """``close > high[1]`` -- the MR script's ``strategy.close("L", comment = "PrevHigh")``.

    Bar 0 has no previous high, so it is ``False``; Pine's ``high[1]`` is ``na`` there and the
    comparison ``close > na`` is false as well.
    """
    out = np.zeros(len(chart), dtype=np.bool_)
    out[1:] = chart.close[1:] > chart.high[:-1]
    return out


#: The Pine exit *signals* that have no registered exit component, by the name a parity config
#: uses. Entry rules are never in here: an entry without a registered component stops the task
#: (T11 §3), because a new component is T07's contract.
PARITY_EXIT_RULES: dict[str, Any] = {
    "close_above_prev_high": _close_above_previous_high,
}


def exit_signal_array(strategy: StrategyRef, chart: ChartData) -> np.ndarray | None:
    """The bool-per-bar exit signal ``run_backtest`` needs, or ``None`` when there is none."""
    name = strategy.exit_signal
    if not name:
        return None
    rule = PARITY_EXIT_RULES.get(name)
    if rule is None:
        raise ConfigError(
            f"unknown parity exit rule {name!r}; known: {sorted(PARITY_EXIT_RULES)} "
            "(a new rule is a Pine rule that has to be read from the script, not invented)"
        )
    return np.asarray(rule(chart), dtype=np.bool_)


def backtest_spec(strategy: StrategyRef) -> BacktestSpec:
    """The ``BacktestSpec`` for a mapped Pine strategy (T11 §3)."""
    spec = ExitSpec.model_validate(strategy.exit)
    if spec.signal_exit and not strategy.exit_signal:
        raise ConfigError(
            "the strategy's exit spec uses signal_exit, so the parity config must name the "
            f"Pine exit rule: exit_signal: one of {sorted(PARITY_EXIT_RULES)} (D-370)"
        )
    if strategy.exit_signal and not spec.signal_exit:
        raise ConfigError(
            f"exit_signal {strategy.exit_signal!r} is set but the exit spec does not use "
            "signal_exit, so the rule would never fire"
        )
    return BacktestSpec(entry=strategy.entry, entry_params=strategy.entry_params, exit=spec)


@dataclass(frozen=True)
class ParityRun:
    """One reference, run and compared. Everything the gate and the report need."""

    config: ParityConfig
    chart: ChartData
    tv: TradeList
    result: RunResult
    comparison: Comparison
    verdict: Verdict

    @property
    def daily(self) -> bool:
        return self.config.reference.timeframe == "1D"


def run_reference(config: ParityConfig, folder: Any = None) -> ParityRun:
    """Load the reference fixtures, run the engine on them and compare (T11 §4).

    ``folder`` defaults to the committed fixtures (D-359). The chart export is used **exactly
    as exported** -- no resampling, no Sunday merge, no shift of the stamps (D-363).
    """
    if config.strategy is None:
        raise ConfigError(
            f"parity config {config.name!r} has no strategy block: the Pine script has not been "
            "mapped to a registered component yet (T11 §3, D-361)"
        )
    if config.reference.trade_list is None:
        raise ConfigError(
            f"parity config {config.name!r} has no reference.trade_list: the Strategy Tester "
            "export has not arrived yet, so the gate cannot run it (D-360 -- this is a loud "
            "failure on purpose, never a skip)"
        )
    chart_path = (
        fixture(config.reference.chart_data)
        if folder is None
        else (folder / config.reference.chart_data)
    )
    name = config.reference.trade_list
    trades_path = fixture(name) if folder is None else (folder / name)
    manifest = load_manifest(chart_path.parent)
    chart = load_chart_data(chart_path, manifest)
    read = load_strategy_report if trades_path.suffix.lower() == ".xlsx" else load_trade_list
    tv = read(trades_path, config.pine.tz(), manifest)

    bars = chart.bars()
    result = run_backtest(
        bars,
        backtest_spec(config.strategy),
        parity_cost_arrays(config.pine, len(chart)),
        symbol=config.reference.symbol,
        timeframe=config.reference.timeframe,
        direction=config.strategy.direction,
        intrabar_mode=config.intrabar_mode,
        exit_signal=exit_signal_array(config.strategy, chart),
        config=config.engine,
    )
    comparison = compare(
        chart,
        tv,
        result,
        tick_size=config.pine.tick_size,
        daily=config.reference.timeframe == "1D",
        qty_step=config.engine.parity_qty_step,
    )
    return ParityRun(
        config=config,
        chart=chart,
        tv=tv,
        result=result,
        comparison=comparison,
        verdict=verdict(
            config,
            matched_share=comparison.matched_share,
            engine_net=comparison.engine_net_profit,
            tv_net=comparison.tv_net_profit,
        ),
    )
