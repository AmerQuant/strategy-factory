"""Naive reference engine: the mandatory T08 oracle (D-330).

Plain Python, one bar at a time, written from the rules of ``docs/tasks/T08_engine.md`` and
the decisions D-001 ... D-004, D-130, D-300, D-307, D-312 ... D-316, D-326 ... D-338. It
shares no code with ``strategy_factory.engine`` (it does not import it) and is deliberately
structured differently (explicit event lists, a position object, no pre-allocated buffers).
Speed does not matter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

SIGNAL, STOP_LOSS, TAKE_PROFIT, DISASTER_STOP, TIME_EXIT, TRAILING_STOP = 0, 1, 2, 3, 4, 5
# ties between stops at the same level: stop loss, then trailing, then disaster
STOP_PRIORITY = {STOP_LOSS: 0, TRAILING_STOP: 1, DISASTER_STOP: 2}


def commission(code: int, p: tuple[float, float, float], qty: float, price: float) -> float:
    q = abs(qty)
    if code == 0:
        return 0.0
    if code == 1:
        return p[0] * q * price
    if code == 2:
        return min(max(p[0] * q, p[1]), p[2])
    if code == 3:
        return q / p[0] * p[1]
    if code == 4:
        return p[0]
    raise ValueError(code)


@dataclass
class Position:
    entry_bar: int
    base: float  # raw open of the entry bar
    fill: float
    qty: float
    atr: float  # ATR of the signal bar
    stops: dict[int, float]  # reason -> level
    target: float | None
    trail_mult: float | None
    extreme: float
    entry_costs: dict[str, float]
    swap: float = 0.0  # USD, + = charge
    best: float = 0.0  # favourable distance
    worst: float = 0.0  # adverse distance


@dataclass
class Trade:
    entry_idx: int
    exit_idx: int
    qty: float
    entry_price: float
    exit_price: float
    pnl_gross: float
    cost_spread: float
    cost_slippage: float
    cost_commission: float
    cost_swap: float
    pnl_net: float
    exit_reason: int
    mae: float
    mfe: float
    atr_at_entry: float


@dataclass
class NaiveResult:
    trades: list[Trade] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    in_position: list[bool] = field(default_factory=list)
    realized: list[float] = field(default_factory=list)
    open_pnl_end: float = 0.0
    n_skipped: int = 0


def run(
    *,
    o: Any, h: Any, lo: Any, c: Any, atr: Any, entry: Any, exit_: Any, direction: int,
    time_exit: int = 0, sl: float | None = None, tp: float | None = None,
    trail: float | None = None, disaster: float,
    half_spread: Any, slip_fixed: Any, slip_frac: float, swap_long: Any, swap_short: Any,
    rollover: Any, triple: Any, comm_code: int = 0,
    comm_p: tuple[float, float, float] = (0.0, 0.0, 0.0), comm_in_quote: bool = False,
    fx_open: Any = None, fx_close: Any = None, sizing: str = "research",
    notional: float = 100_000.0, contracts: float = 1.0, point_value: float = 1.0,
    contract_size: float = 1.0, step: float = 1.0, min_volume: float = 1.0,
    step_tol: float = 1e-9, capital: float = 100_000.0, mode: str = "pessimistic",
) -> NaiveResult:  # fmt: skip
    n = len(c)
    fxo = [1.0] * n if fx_open is None else [float(x) for x in fx_open]
    fxc = [1.0] * n if fx_close is None else [float(x) for x in fx_close]
    dr = float(direction)
    res = NaiveResult()
    pos: Position | None = None
    want_exit: int | None = None  # reason of an exit scheduled for the next open
    want_entry = False
    realized = 0.0

    def fill_cost(j: int) -> float:
        return half_spread[j] + slip_fixed[j] + slip_frac * atr[j - 1]

    def close_position(j: int, base: float, reason: int, extra_swap: float) -> None:
        nonlocal pos, realized
        assert pos is not None
        p = pos
        f = fxc[j]
        gap = dr * (base - p.base)
        p.best = max(p.best, gap)
        p.worst = max(p.worst, -gap)
        exit_fill = base - dr * fill_cost(j)
        spread = p.entry_costs["spread"] + p.qty * half_spread[j] * point_value * f
        slip = (
            p.entry_costs["slip"]
            + p.qty * (slip_fixed[j] + slip_frac * atr[j - 1]) * point_value * f
        )
        cx = commission(comm_code, comm_p, p.qty, exit_fill)
        comm = p.entry_costs["comm"] + (cx * f if comm_in_quote else cx)
        swap = p.swap + extra_swap
        gross = dr * p.qty * (base - p.base) * point_value * f
        net = gross - (spread + slip + comm + swap)
        res.trades.append(
            Trade(
                p.entry_bar,
                j,
                p.qty,
                p.fill,
                exit_fill,
                gross,
                spread,
                slip,
                comm,
                swap,
                net,
                reason,
                p.worst * p.qty * point_value * f,
                p.best * p.qty * point_value * f,
                p.atr,
            )
        )
        realized += net
        pos = None

    for j in range(n):
        # 1) open: scheduled exit, else gaps; then a scheduled entry
        if pos is not None:
            if want_exit is not None:
                close_position(j, o[j], want_exit, 0.0)
            else:
                crossed = [
                    (r, lv) for r, lv in pos.stops.items() if (o[j] <= lv if dr > 0 else o[j] >= lv)
                ]
                if crossed:
                    r = sorted(crossed, key=lambda x: (-dr * x[1], STOP_PRIORITY[x[0]]))[0][0]
                    close_position(j, o[j], r, 0.0)
                elif pos.target is not None and (
                    o[j] >= pos.target if dr > 0 else o[j] <= pos.target
                ):
                    close_position(j, o[j], TAKE_PROFIT, 0.0)
        want_exit = None
        if want_entry and pos is None:
            want_entry = False
            s = j - 1
            if sizing == "research":
                steps = notional / (o[j] * fxo[j] * contract_size) / step
                k_steps = math.floor(steps * (1 + step_tol))
                qty = k_steps * step * contract_size
                ok = k_steps >= math.ceil(min_volume / step * (1 - step_tol))
            elif sizing == "contracts":
                qty, ok = contracts, True
            else:  # parity
                qty = notional / (c[s] * fxc[s])
                ok = qty > 0
            if not ok:
                res.n_skipped += 1
            else:
                a = atr[s]
                base = o[j]
                stops = {DISASTER_STOP: base - dr * disaster * a}
                if sl is not None:
                    stops[STOP_LOSS] = base - dr * sl * a
                if trail is not None:
                    stops[TRAILING_STOP] = base - dr * trail * a
                fill = base + dr * fill_cost(j)
                cm = commission(comm_code, comm_p, qty, fill)
                pos = Position(
                    j, base, fill, qty, a, stops,
                    None if tp is None else base + dr * tp * a, trail, base,
                    {
                        "spread": qty * half_spread[j] * point_value * fxc[j],
                        "slip": qty * (slip_fixed[j] + slip_frac * a) * point_value * fxc[j],
                        "comm": cm * fxc[j] if comm_in_quote else cm,
                    },
                )  # fmt: skip
        want_entry = False
        # 2) intrabar
        if pos is not None:
            adverse = lo[j] if dr > 0 else h[j]
            hit_stops = [
                (r, lv)
                for r, lv in pos.stops.items()
                if (adverse <= lv if dr > 0 else adverse >= lv)
            ]
            favour = h[j] if dr > 0 else lo[j]
            hit_tp = pos.target is not None and (
                favour >= pos.target if dr > 0 else favour <= pos.target
            )
            choice: tuple[int, float] | None = None
            if hit_stops:
                stop = sorted(hit_stops, key=lambda x: (-dr * x[1], STOP_PRIORITY[x[0]]))[0]
            if hit_stops and hit_tp:
                if mode == "tradingview":
                    high_first = (h[j] - o[j]) < (o[j] - lo[j])
                    low_first = (o[j] - lo[j]) < (h[j] - o[j])
                    target_first = high_first if dr > 0 else low_first
                    choice = (TAKE_PROFIT, pos.target) if target_first else stop  # type: ignore[assignment]
                else:
                    choice = stop
            elif hit_stops:
                choice = stop
            elif hit_tp:
                choice = (TAKE_PROFIT, pos.target)  # type: ignore[assignment]
            if choice is not None:
                extra = 0.0
                if rollover[j] and mode == "pessimistic":
                    rate = swap_long[j] if dr > 0 else swap_short[j]
                    if rate < 0:
                        extra = (
                            -rate * (3 if triple[j] else 1) * pos.qty * c[j] * point_value * fxc[j]
                        )
                close_position(j, choice[1], choice[0], extra)
        # 3) close
        open_pnl = 0.0
        if pos is not None:
            p = pos
            p.best = max(p.best, dr * ((h[j] if dr > 0 else lo[j]) - p.base))
            p.worst = max(p.worst, -dr * ((lo[j] if dr > 0 else h[j]) - p.base))
            if rollover[j]:
                rate = swap_long[j] if dr > 0 else swap_short[j]
                p.swap -= rate * (3 if triple[j] else 1) * p.qty * c[j] * point_value * fxc[j]
            if p.trail_mult is not None:
                p.extreme = max(p.extreme, h[j]) if dr > 0 else min(p.extreme, lo[j])
                new = p.extreme - dr * p.trail_mult * p.atr
                if dr * (new - p.stops[TRAILING_STOP]) > 0:
                    p.stops[TRAILING_STOP] = new
            if exit_[j]:
                want_exit = SIGNAL
            elif time_exit and j - p.entry_bar + 1 >= time_exit:
                want_exit = TIME_EXIT
            costs = p.entry_costs["spread"] + p.entry_costs["slip"] + p.entry_costs["comm"] + p.swap
            open_pnl = dr * p.qty * (c[j] - p.base) * point_value * fxc[j] - costs
        flat_or_leaving = pos is None or want_exit is not None
        if entry[j] and j < n - 1 and atr[j] > 0 and flat_or_leaving:
            want_entry = True
        res.equity.append(capital + realized + open_pnl)
        res.in_position.append(pos is not None)
        res.realized.append(realized)
    if pos is not None:
        res.open_pnl_end = res.equity[-1] - capital - realized
    return res
