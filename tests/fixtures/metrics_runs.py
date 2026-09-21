"""Builders for metrics tests: the hand-computed 3-year fixture and random consistent runs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from hypothesis import strategies as st

from strategy_factory.metrics.containers import (
    EquityCurve,
    ExitReason,
    RunMeta,
    RunResult,
    TradeLog,
)

CAPITAL = 100_000.0
NOTIONAL = 100_000.0


def meta(cost_status: str = "verified") -> RunMeta:
    return RunMeta(
        symbol="TEST",
        timeframe="1d",
        spec_hash="0" * 64,
        cost_status=cost_status,  # type: ignore[arg-type]
        intrabar_mode="pessimistic",
    )


def trade_log(rows: list[dict[str, Any]]) -> TradeLog:
    """TradeLog from row dicts; ``bars_held`` and missing diagnostics are filled in."""
    if not rows:
        return TradeLog.empty()
    defaults = {
        "direction": 1,
        "qty": 1000.0,
        "cost_spread": 0.0,
        "cost_slippage": 0.0,
        "cost_commission": 0.0,
        "cost_swap": 0.0,
        "exit_reason": int(ExitReason.SIGNAL),
        "mae": 0.0,
        "mfe": 0.0,
        "atr_at_entry": 1.0,
    }
    full = [{**defaults, **r} for r in rows]
    for r in full:
        r.setdefault("bars_held", r["exit_idx"] - r["entry_idx"])
        costs = r["cost_spread"] + r["cost_slippage"] + r["cost_commission"] + r["cost_swap"]
        r.setdefault("pnl_gross", r["pnl_net"] + costs)
        r.setdefault("entry_price", 100.0)
        r.setdefault("exit_price", r["entry_price"] + r["direction"] * r["pnl_gross"] / r["qty"])
    cols = {k: np.array([r[k] for r in full]) for k in full[0]}
    return TradeLog(**cols)


# --------------------------------------------------------------------------- hand fixture
# 10 daily bars over 2021-07-02 .. 2023-07-02 (730 days). Trades:
#   T1 long  entry bar 1 (2021-10-01) exit bar 3 (2022-03-01): pnl_net -500 (spans a year end)
#   T2 short entry bar 4 (2022-06-01) exit bar 7 (2023-02-01): pnl_net +9500
#   T3 long  entry bar 8 (2023-04-01), still open at the last bar: open P&L +2000
HAND_TS = np.array(
    [
        "2021-07-02",
        "2021-10-01",
        "2021-12-31",
        "2022-03-01",
        "2022-06-01",
        "2022-09-01",
        "2022-12-30",
        "2023-02-01",
        "2023-04-01",
        "2023-07-02",
    ],
    dtype="datetime64[ns]",
)
HAND_EQUITY = np.array(
    [100000, 105000, 102000, 99500, 108000, 104000, 110000, 109000, 112000, 111000],
    dtype=np.float64,
)
HAND_IN_POS = np.array([0, 1, 1, 0, 1, 1, 1, 0, 1, 1], dtype=bool)
HAND_REALIZED = np.array([0, 0, 0, -500, -500, -500, -500, 9000, 9000, 9000], dtype=np.float64)


def hand_trades() -> TradeLog:
    return trade_log(
        [
            {
                "entry_idx": 1,
                "exit_idx": 3,
                "entry_ts": HAND_TS[1],
                "exit_ts": HAND_TS[3],
                "direction": 1,
                "pnl_net": -500.0,
                "cost_spread": 100.0,
                "cost_slippage": 50.0,
                "cost_commission": 40.0,
                "cost_swap": 10.0,
                "atr_at_entry": 2.0,
                "exit_reason": int(ExitReason.STOP_LOSS),
            },
            {
                "entry_idx": 4,
                "exit_idx": 7,
                "entry_ts": HAND_TS[4],
                "exit_ts": HAND_TS[7],
                "direction": -1,
                "entry_price": 110.0,
                "pnl_net": 9500.0,
                "cost_spread": 100.0,
                "cost_slippage": 50.0,
                "cost_commission": 40.0,
                "cost_swap": 10.0,
                "atr_at_entry": 5.0,
            },
        ]
    )


def hand_run(cost_status: str = "verified") -> RunResult:
    curve = EquityCurve(
        ts=HAND_TS,
        equity_mtm=HAND_EQUITY,
        in_position=HAND_IN_POS,
        realized_pnl=HAND_REALIZED,
        initial_capital=CAPITAL,
        notional=NOTIONAL,
        open_pnl_end=2000.0,
    )
    return RunResult(trades=hand_trades(), equity=curve, meta=meta(cost_status))


# --------------------------------------------------------------------------- random runs
STEPS_NS = {
    "1h": np.timedelta64(1, "h").astype("timedelta64[ns]"),
    "1d": np.timedelta64(1, "D").astype("timedelta64[ns]"),
    "3d": np.timedelta64(3, "D").astype("timedelta64[ns]"),
}


@dataclass(frozen=True)
class RunSpec:
    """Plain description of a consistent random run.

    Gaps >= 1 (no back-to-back trades); a hold of 0 is a same-bar trade stopped out intrabar.
    """

    start: np.datetime64
    steps: tuple[str, ...]  # len n - 1
    trades: tuple[tuple[int, int], ...]  # (gap before entry, bars held)
    increments: tuple[float, ...]  # len n: MTM P&L change of each in-position / exit bar
    costs: tuple[float, ...]  # per trade: commission charged at exit
    #: position size of every trade. The entry price is fixed (1000) and the exit price is
    #: derived from the gross P&L, so the price move per unit is ``gross / qty``: bounded by
    #: 13 bars x 3000 / 100 = 390, which keeps every derived price in (610, 1390).
    qty: float = 100.0

    @property
    def n(self) -> int:
        return len(self.increments)

    def scaled(self, k: float) -> RunSpec:
        """The same run with a position ``k`` times the size (D-368).

        P&L and costs scale by ``k`` **because the position does**: ``qty`` scales with them,
        so every derived price is unchanged. Scaling the P&L at a fixed ``qty`` would move the
        price level instead -- by ``k`` times -- and a large enough ``k`` drives an exit price
        to zero or below, which ``TradeLog`` rightly refuses.
        """
        return replace(
            self,
            increments=tuple(k * x for x in self.increments),
            costs=tuple(k * c for c in self.costs),
            qty=k * self.qty,
        )

    def with_extra_cost(self, trade: int, cost: float) -> RunSpec:
        costs = list(self.costs)
        costs[trade] += cost
        return replace(self, costs=tuple(costs))

    def ts(self) -> np.ndarray:
        deltas = [np.timedelta64(0, "ns")] + [STEPS_NS[s] for s in self.steps]
        return np.datetime64(self.start, "ns") + np.cumsum(np.array(deltas))

    def windows(self) -> list[tuple[int, int]]:
        """(entry_idx, exit_idx) of each trade; exit_idx == n means open at the end."""
        out, pos = [], 0
        for gap, hold in self.trades:
            entry = pos + gap
            if entry > self.n - 1:
                break
            out.append((entry, min(entry + hold, self.n)))
            pos = entry + hold
            if pos >= self.n:
                break
        return out


def build_run(spec: RunSpec) -> RunResult:
    n, ts = spec.n, spec.ts()
    equity = np.empty(n)
    in_pos = np.zeros(n, dtype=bool)
    realized = np.empty(n)
    rows: list[dict[str, Any]] = []
    windows = spec.windows()
    closed = {exit_idx: i for i, (_, exit_idx) in enumerate(windows) if exit_idx < n}
    active = {t: i for i, (e, x) in enumerate(windows) for t in range(e, x)}
    real, open_pnl = 0.0, 0.0
    for t in range(n):
        if t in closed:
            i = closed[t]
            gross = open_pnl + spec.increments[t]
            cost = spec.costs[i]
            real += gross - cost
            entry = windows[i][0]
            rows.append(
                {
                    "entry_idx": entry,
                    "exit_idx": t,
                    "entry_ts": ts[entry],
                    "exit_ts": ts[t],
                    "direction": 1 if i % 2 == 0 else -1,
                    "qty": spec.qty,
                    "entry_price": 1000.0,
                    "pnl_gross": gross,
                    "cost_commission": cost,
                    "pnl_net": gross - cost,
                    "atr_at_entry": 10.0,
                    "exit_reason": int(ExitReason.STOP_LOSS if t == entry else ExitReason.SIGNAL),
                }
            )
            open_pnl = 0.0
        if t in active:
            open_pnl += spec.increments[t]
            in_pos[t] = True
        realized[t] = real
        equity[t] = CAPITAL + real + open_pnl
    curve = EquityCurve(
        ts=ts,
        equity_mtm=equity,
        in_position=in_pos,
        realized_pnl=realized,
        initial_capital=CAPITAL,
        notional=NOTIONAL,
        open_pnl_end=open_pnl if in_pos[-1] else 0.0,
    )
    return RunResult(trades=trade_log(rows), equity=curve, meta=meta())


money = st.integers(min_value=-3000, max_value=3000).map(float)


@st.composite
def run_specs(
    draw: st.DrawFn, n: int | None = None, steps: tuple[str, ...] | None = None
) -> RunSpec:
    size = n if n is not None else draw(st.integers(min_value=2, max_value=250))
    if steps is None:
        steps = tuple(
            draw(st.lists(st.sampled_from(sorted(STEPS_NS)), min_size=size - 1, max_size=size - 1))
        )
    start_day = draw(st.integers(min_value=0, max_value=3000))
    start = np.datetime64("2015-01-01", "ns") + np.timedelta64(start_day, "D")
    trades = tuple(
        draw(st.lists(st.tuples(st.integers(1, 15), st.integers(0, 12)), min_size=0, max_size=30))
    )
    increments = tuple(draw(st.lists(money, min_size=size, max_size=size)))
    costs = tuple(
        draw(st.lists(st.integers(0, 300).map(float), min_size=len(trades), max_size=len(trades)))
    )
    return RunSpec(start=start, steps=steps, trades=trades, increments=increments, costs=costs)


def rising_run() -> RunResult:
    """Zero-drawdown run on HAND_TS: one trade (bars 1..8) with equity rising 100 per bar."""
    equity = CAPITAL + 100.0 * np.arange(10)
    in_pos = np.array([0, 1, 1, 1, 1, 1, 1, 1, 1, 0], dtype=bool)
    realized = np.where(np.arange(10) == 9, 900.0, 0.0)
    curve = EquityCurve(
        ts=HAND_TS,
        equity_mtm=equity,
        in_position=in_pos,
        realized_pnl=realized,
        initial_capital=CAPITAL,
        notional=NOTIONAL,
    )
    trades = trade_log(
        [
            {
                "entry_idx": 1,
                "exit_idx": 9,
                "entry_ts": HAND_TS[1],
                "exit_ts": HAND_TS[9],
                "pnl_net": 900.0,
            }
        ]
    )
    return RunResult(trades=trades, equity=curve, meta=meta("placeholder"))
