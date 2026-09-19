"""F-0.5.1: result containers (engine output contract) validate and round-trip."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fixtures.metrics_runs import (
    CAPITAL,
    HAND_EQUITY,
    HAND_IN_POS,
    HAND_REALIZED,
    HAND_TS,
    NOTIONAL,
    hand_run,
    hand_trades,
    meta,
)

from strategy_factory.metrics.artifacts import read_run_result, write_run_result
from strategy_factory.metrics.containers import (
    ContainerError,
    EquityCurve,
    RunResult,
    TradeLog,
)


def _trade_cols(**override: Any) -> dict[str, Any]:
    cols = {k: np.array(v, copy=True) for k, v in hand_trades().columns().items()}
    cols.update({k: np.asarray(v) for k, v in override.items()})
    return cols


def _curve(**override: Any) -> EquityCurve:
    kwargs: dict[str, Any] = {
        "ts": HAND_TS,
        "equity_mtm": HAND_EQUITY,
        "in_position": HAND_IN_POS,
        "realized_pnl": HAND_REALIZED,
        "initial_capital": CAPITAL,
        "notional": NOTIONAL,
        "open_pnl_end": 2000.0,
    }
    kwargs.update(override)
    return EquityCurve(**kwargs)


def test_F_0_5_1_hand_run_is_valid() -> None:
    run = hand_run()
    assert len(run.trades) == 2
    assert run.open_position_marked
    assert not run.equity.equity_mtm.flags.writeable
    assert not run.trades.pnl_net.flags.writeable


def test_F_0_5_1_pnl_net_must_equal_gross_minus_costs() -> None:
    cols = _trade_cols()
    cols["pnl_net"] = cols["pnl_net"] + np.array([0.0, 1.0])
    with pytest.raises(ContainerError, match="pnl_net"):
        TradeLog(**cols)


def test_F_0_5_1_swap_credit_allowed_in_net_identity() -> None:
    cols = _trade_cols(cost_swap=[-10.0, 10.0])
    cols["pnl_net"] = cols["pnl_gross"] - (
        cols["cost_spread"] + cols["cost_slippage"] + cols["cost_commission"] + cols["cost_swap"]
    )
    assert len(TradeLog(**cols)) == 2


@pytest.mark.parametrize("exit_idx", [[1, 7], [0, 7]])
def test_F_0_5_1_exit_idx_at_least_entry_plus_one(exit_idx: list[int]) -> None:
    cols = _trade_cols(exit_idx=exit_idx)
    cols["bars_held"] = cols["exit_idx"] - cols["entry_idx"]
    with pytest.raises(ContainerError, match="exit_idx"):
        TradeLog(**cols)


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"bars_held": [3, 3]}, "bars_held"),
        ({"direction": [1, 0]}, "direction"),
        ({"qty": [0.0, 1000.0]}, "qty"),
        ({"atr_at_entry": [0.0, 5.0]}, "atr_at_entry"),
        ({"exit_reason": [0, 99]}, "exit_reason"),
        ({"mae": [-1.0, 0.0]}, "mae"),
        ({"entry_price": [np.nan, 110.0]}, "non-finite"),
        ({"entry_idx": [1, 2], "bars_held": [2, 5]}, "overlap"),
    ],
)
def test_F_0_5_1_trade_log_rejects(override: dict[str, Any], match: str) -> None:
    with pytest.raises(ContainerError, match=match):
        TradeLog(**_trade_cols(**override))


def test_F_0_5_1_trade_log_column_lengths_must_match() -> None:
    with pytest.raises(ContainerError, match="length"):
        TradeLog(**_trade_cols(mfe=[0.0]))


def test_F_0_5_1_ts_strictly_increasing() -> None:
    ts = HAND_TS.copy()
    ts[5] = ts[4]
    with pytest.raises(ContainerError, match="strictly increasing"):
        _curve(ts=ts)
    with pytest.raises(ContainerError, match="datetime64"):
        _curve(ts=np.arange(10))


def test_F_0_5_1_final_equity_identity() -> None:
    # wrong open P&L at the end
    with pytest.raises(ContainerError, match="final equity"):
        _curve(open_pnl_end=1999.0)
    # a flat bar whose equity disagrees with capital + realized
    eq = HAND_EQUITY.copy()
    eq[0] = 100_001.0
    with pytest.raises(ContainerError, match="flat bars"):
        _curve(equity_mtm=eq)
    # open_pnl_end must be 0 when flat at the end
    pos = HAND_IN_POS.copy()
    pos[-1] = False
    with pytest.raises(ContainerError):
        _curve(in_position=pos)


def test_F_0_5_1_realized_must_match_trade_log() -> None:
    cols = _trade_cols(cost_commission=[40.0, 41.0])
    cols["pnl_net"] = cols["pnl_net"] - np.array([0.0, 1.0])
    trades = TradeLog(**cols)
    with pytest.raises(ContainerError, match="sum\\(pnl_net\\)"):
        RunResult(trades=trades, equity=_curve(), meta=meta())


def test_F_0_5_1_trade_ts_must_match_curve() -> None:
    cols = _trade_cols()
    cols["exit_ts"] = cols["exit_ts"] + np.timedelta64(1, "h")
    with pytest.raises(ContainerError, match="exit_ts"):
        RunResult(trades=TradeLog(**cols), equity=_curve(), meta=meta())


def test_F_0_5_1_in_position_must_match_trades() -> None:
    pos = HAND_IN_POS.copy()
    pos[5] = False  # bar 5 is inside T2 (entry 4, exit 7)
    eq = HAND_EQUITY.copy()
    eq[5] = CAPITAL + HAND_REALIZED[5]
    with pytest.raises(ContainerError, match="in_position"):
        RunResult(trades=hand_trades(), equity=_curve(in_position=pos, equity_mtm=eq), meta=meta())


def test_F_0_5_1_exit_beyond_curve_rejected() -> None:
    curve = _curve(
        ts=HAND_TS[:6],
        equity_mtm=HAND_EQUITY[:6],
        in_position=HAND_IN_POS[:6],
        realized_pnl=HAND_REALIZED[:6],
        open_pnl_end=HAND_EQUITY[5] - CAPITAL - HAND_REALIZED[5],
    )
    with pytest.raises(ContainerError, match="beyond"):
        RunResult(trades=hand_trades(), equity=curve, meta=meta())


def test_F_0_5_1_parquet_round_trip(tmp_path: Path) -> None:
    run = hand_run()
    target = write_run_result(run, tmp_path / "artifact")
    back = read_run_result(target)
    for f in fields(TradeLog):
        np.testing.assert_array_equal(getattr(back.trades, f.name), getattr(run.trades, f.name))
    for name in ("ts", "equity_mtm", "in_position", "realized_pnl"):
        np.testing.assert_array_equal(getattr(back.equity, name), getattr(run.equity, name))
    assert back.equity.open_pnl_end == run.equity.open_pnl_end
    assert back.meta == run.meta
    # artifacts are immutable: a second write to the same directory raises
    with pytest.raises(FileExistsError):
        write_run_result(run, target)


def test_F_0_5_1_parquet_round_trip_empty_trades(tmp_path: Path) -> None:
    ts = HAND_TS[:3]
    curve = EquityCurve(
        ts=ts,
        equity_mtm=np.full(3, CAPITAL),
        in_position=np.zeros(3, dtype=bool),
        realized_pnl=np.zeros(3),
        initial_capital=CAPITAL,
        notional=NOTIONAL,
    )
    run = RunResult(trades=TradeLog.empty(), equity=curve, meta=meta())
    back = read_run_result(write_run_result(run, tmp_path / "a"))
    assert len(back.trades) == 0
    np.testing.assert_array_equal(back.equity.ts, ts)
