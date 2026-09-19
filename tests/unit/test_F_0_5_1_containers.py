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
    trade_log,
)

from strategy_factory.data.result_io import read_run_result, write_run_result
from strategy_factory.metrics.containers import (
    INTRABAR_EXIT_REASONS,
    ContainerError,
    EquityCurve,
    ExitReason,
    RunMeta,
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


def _same_bar_first_trade(reason: ExitReason) -> dict[str, Any]:
    """Hand trades with T1 (entry bar 1) exiting inside its entry bar for ``reason``."""
    cols = _trade_cols(exit_idx=[1, 7], exit_reason=[int(reason), int(ExitReason.SIGNAL)])
    cols["bars_held"] = cols["exit_idx"] - cols["entry_idx"]
    cols["exit_ts"] = cols["entry_ts"].copy()
    cols["exit_ts"][1] = HAND_TS[7]
    return cols


@pytest.mark.parametrize(
    "reason",
    [
        ExitReason.DISASTER_STOP,
        ExitReason.STOP_LOSS,
        ExitReason.TAKE_PROFIT,
        ExitReason.TRAILING_STOP,
    ],
)
def test_F_0_5_1_same_bar_exit_allowed_for_intrabar_reasons(reason: ExitReason) -> None:
    assert reason in INTRABAR_EXIT_REASONS
    trades = TradeLog(**_same_bar_first_trade(reason))
    assert trades.bars_held.tolist() == [0, 3]


@pytest.mark.parametrize("reason", [ExitReason.SIGNAL, ExitReason.TIME_EXIT])
def test_F_0_5_1_same_bar_exit_rejected_for_signal_and_time(reason: ExitReason) -> None:
    assert reason not in INTRABAR_EXIT_REASONS
    with pytest.raises(ContainerError, match="intrabar"):
        TradeLog(**_same_bar_first_trade(reason))


@pytest.mark.parametrize("reason", list(ExitReason))
def test_F_0_5_1_exit_before_entry_always_rejected(reason: ExitReason) -> None:
    cols = _trade_cols(exit_idx=[0, 7], exit_reason=[int(reason), int(ExitReason.SIGNAL)])
    cols["bars_held"] = cols["exit_idx"] - cols["entry_idx"]
    with pytest.raises(ContainerError, match="exit_idx must be >= entry_idx"):
        TradeLog(**cols)


def test_F_0_5_1_same_bar_trade_in_run_occupies_no_bar() -> None:
    # T1 is stopped out inside its entry bar 1: flat at every close, realized from bar 1 on
    ts = HAND_TS[:4]
    trades = trade_log(
        [
            {
                "entry_idx": 1,
                "exit_idx": 1,
                "entry_ts": ts[1],
                "exit_ts": ts[1],
                "pnl_net": -300.0,
                "exit_reason": int(ExitReason.DISASTER_STOP),
            }
        ]
    )
    realized = np.array([0.0, -300.0, -300.0, -300.0])
    curve = EquityCurve(
        ts=ts,
        equity_mtm=CAPITAL + realized,
        in_position=np.zeros(4, dtype=bool),
        realized_pnl=realized,
        initial_capital=CAPITAL,
        notional=NOTIONAL,
    )
    run = RunResult(trades=trades, equity=curve, meta=meta())
    assert len(run.trades) == 1
    # a signal exit on the same bar is rejected before the run is even built
    with pytest.raises(ContainerError, match="intrabar"):
        trade_log(
            [
                {
                    "entry_idx": 1,
                    "exit_idx": 1,
                    "entry_ts": ts[1],
                    "exit_ts": ts[1],
                    "pnl_net": -300.0,
                    "exit_reason": int(ExitReason.SIGNAL),
                }
            ]
        )


def test_F_0_5_1_two_trades_cannot_enter_on_the_same_bar() -> None:
    cols = _trade_cols(
        entry_idx=[1, 1],
        exit_idx=[1, 7],
        exit_reason=[int(ExitReason.STOP_LOSS), int(ExitReason.SIGNAL)],
    )
    cols["bars_held"] = cols["exit_idx"] - cols["entry_idx"]
    with pytest.raises(ContainerError, match="overlap"):
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


# -- T08 follow-up: exit and re-entry at the same open with the position open at the end ------
def _curve_and_log(in_position: list[bool], exits: list[int], entries: list[int]) -> Any:
    import datetime as _dt

    n = len(in_position)
    ts = np.array(
        [np.datetime64(_dt.datetime(2024, 1, 1) + _dt.timedelta(hours=i), "ns") for i in range(n)]
    )
    k = len(entries)
    z = np.zeros(k)
    log = TradeLog(
        entry_idx=np.array(entries), exit_idx=np.array(exits), entry_ts=ts[entries],
        exit_ts=ts[exits], direction=np.ones(k, np.int64), qty=np.ones(k),
        entry_price=np.full(k, 100.0), exit_price=np.full(k, 100.0), pnl_gross=z,
        cost_spread=z, cost_slippage=z, cost_commission=z, cost_swap=z, pnl_net=z,
        exit_reason=np.zeros(k, np.int64), mae=z, mfe=z, atr_at_entry=np.ones(k),
        bars_held=np.array(exits) - np.array(entries),
    )  # fmt: skip
    curve = EquityCurve(
        ts=ts, equity_mtm=np.full(n, 100_000.0), in_position=np.array(in_position),
        realized_pnl=np.zeros(n), initial_capital=100_000.0, notional=100_000.0,
    )  # fmt: skip
    return log, curve


def test_F_0_5_1_open_position_reentered_at_the_last_exit_open() -> None:
    """D-336: a trade exits at the open of bar 4 and a new position opens at that open and is
    still open at the end: in_position has no flat bar between them (T08 validator fix)."""
    meta = RunMeta(symbol="X", timeframe="1H", spec_hash="h", cost_status="verified",
                   intrabar_mode="pessimistic")  # fmt: skip
    log, curve = _curve_and_log([False, False, True, True, True, True, True], [4], [2])
    RunResult(trades=log, equity=curve, meta=meta)  # accepted
    bad_log, bad_curve = _curve_and_log([False, True, True, True, False, True, True], [4], [2])
    with pytest.raises(ContainerError, match="in_position"):
        RunResult(trades=bad_log, equity=bad_curve, meta=meta)  # bar 1 is not occupied
