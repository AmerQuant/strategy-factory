"""Backtest kernel (F-0.3.1, F-0.3.2, F-0.3.4): arrays in, arrays out (design §6, ADR-001).

One Numba routine, :func:`_core`, simulates one strategy on one series. :func:`simulate_one`
and :func:`simulate_grid_kernel` both call it, so a grid column equals the single run bit for
bit. No files, config, logging or Python objects inside (CLAUDE.md rule 6).

Conventions (task T08, decisions D-001 ... D-004, D-130, D-300, D-307, D-312 ... D-316,
D-326 ... D-338):

* A signal at the close of bar ``i`` fills at the **open of bar i+1** (D-001).
* **Bar j, open:** a scheduled exit fills first, then a scheduled entry (D-336). A held
  position whose stop (or target) the open gapped through exits **at the open**.
* **Bar j, intrabar:** disaster stop, stop loss, trailing stop and take profit via high/low,
  from the entry bar on (a same-bar exit has ``exit_idx == entry_idx``, D-300). Several stops
  touched: the one nearest the open (highest for a long) wins; ties go in the order stop
  loss, trailing, disaster. Stop and target both touched: ``pessimistic`` (mode 1) takes the
  stop; ``tradingview`` (mode 0) goes O->H->L->C when the high is nearer the open, else
  O->L->H->C, and a tie takes the stop (D-335, to_verify).
* **Bar j, close:** signal exit (priority) or time exit is scheduled for ``j+1``; an entry is
  scheduled when flat or when an exit is scheduled (D-336, to_verify), if ``j < n-1`` and
  ``atr[j] > 0`` (warm-up); swap for a position held at the close of a rollover bar on the
  mark-to-market notional ``|qty| x close[j] x point_value x fx_close[j]``, x3 on the
  triple day (D-312). The trailing stop moves to ``extreme since entry -/+ trail x ATR``.
* A stop/target exit **inside** a rollover bar (D-327): pessimistic mode applies that bar's
  swap if it is a charge (never a credit); tradingview mode applies none (to_verify).
* Levels (D-326): from the raw open of the entry bar and ``atr_e = atr[entry - 1]``.
  Every fill in bar ``j`` pays ``half_spread[j] + slippage_fixed[j] + frac x atr[j-1]``.
* Sizing: mode 0 research (D-313, D-315, D-328): ``lots = floor(notional /
  (open[j] x fx_open[j] x contract_size) / step) x step``, ``qty = lots x contract_size``;
  below ``min_volume`` the entry is skipped and counted. Mode 1 futures: ``qty = contracts``
  (D-329). Mode 2 parity (D-337, D-347): ``qty = floor(notional / (close[j-1] x
  fx_close[j-1]) / parity_qty_step) x parity_qty_step``, with the same float guard;
  ``parity_qty_step`` is required per run (BATS:SPY 1, OANDA:XAUUSD 0.01) and the broker step
  and minimum volume are never applied. ``qty = 0`` is a skip.
* Parity choices still marked **to_verify until T11** (D-338 rule 1, D-349): the O->H->L->C
  path and its tie (D-335); exit + re-entry at one open (D-336); no swap on intrabar exits in
  rollover bars (D-327); the trailing level moving only at the close (D-349 (a); final in
  research, to match against the Pine script in parity); and the parity conversion rate
  (D-349 (h)). The sizing basis of D-337 is confirmed by the exports and is no longer
  to_verify; the remaining choices of D-349 ((b)-(g), (i)) are confirmed as implemented.
* Money (USD): ``pnl_gross = dir x qty x (exit_base - entry_base) x point_value x
  fx_close[exit]``; spread and slippage cost ``qty x amount x point_value x fx_close`` of the
  fill bar; commission from :func:`commission_kernel`, converted with ``fx_close`` of the fill
  bar only when it is in the quote currency; ``pnl_net = pnl_gross - costs``. Fill prices
  (``entry_price``/``exit_price``) include half-spread and slippage.
* MAE/MFE (money, >= 0, D-349 (f)): the **high/low** of every bar held at its close
  (entry .. exit-1) and the **exit fill**, relative to the entry base price, converted with
  ``fx_close[exit]``. Diagnostic only (not part of the D-011 parity criterion).
* Equity at each close: capital + realized + ``dir x qty x (close - entry_base) x pv x
  fx_close`` - the entry costs - the swap so far.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit, prange

from strategy_factory.engine.commission import commission_kernel

# ExitReason codes (metrics.containers.ExitReason; pinned by a test, the engine cannot import
# metrics).
SIGNAL = 0
STOP_LOSS = 1
TAKE_PROFIT = 2
DISASTER_STOP = 3
TIME_EXIT = 4
TRAILING_STOP = 5

MODE_TRADINGVIEW = 0
MODE_PESSIMISTIC = 1
SIZE_RESEARCH = 0
SIZE_CONTRACTS = 1
SIZE_PARITY = 2


@njit(cache=True)
def research_lots(notional_usd, price_usd, contract_size, volume_step, min_volume, step_tol):
    """D-315 floor to the volume step; returns (lots, skipped). Same arithmetic as
    ``costs.arrays.size_lots``."""
    steps = notional_usd / (price_usd * contract_size) / volume_step
    n = math.floor(steps * (1.0 + step_tol))
    lots = n * volume_step
    min_steps = math.ceil(min_volume / volume_step * (1.0 - step_tol))
    return lots, n < min_steps


@njit(cache=True)
def _ticks(distance, tick):
    """``distance`` as whole ticks, rounded half **away from zero** like Pine's ``math.round``.

    Pine writes stop and target distances as ``math.round(k * atr / syminfo.mintick)``; the
    level is then that many ticks from the fill. ``math.floor(x + 0.5)`` is half-up, which for
    a non-negative distance is half away from zero.
    """
    if tick <= 0.0:
        return distance
    return math.floor(abs(distance) / tick + 0.5) * tick


@njit(cache=True)
def _core(
    open_, high, low, close, atr, entry_sig, exit_sig, direction,
    time_exit_bars, sl_atr, tp_atr, trail_atr, disaster_atr,
    half_spread, slip_fixed, slip_atr_frac, swap_long, swap_short, rollover, triple,
    c_code, c_p0, c_p1, c_p2, comm_in_quote,
    fx_open, fx_close, sizing_mode, notional, contracts, point_value,
    contract_size, volume_step, min_volume, parity_qty_step, step_tol,
    initial_capital, intrabar_mode, parity_tick, entry_requires_flat, record,
    t_entry, t_exit, t_qty, t_entry_price, t_exit_price, t_gross, t_spread, t_slip,
    t_comm, t_swap, t_net, t_reason, t_mae, t_mfe, t_atr,
    equity, in_pos, realized_out,
):  # fmt: skip
    n = open_.shape[0]
    d = float(direction)
    use_sl = not math.isnan(sl_atr)
    use_tp = not math.isnan(tp_atr)
    use_trail = not math.isnan(trail_atr)

    in_trade = False
    pend_entry = False
    pend_exit = False
    pend_reason = SIGNAL
    n_trades = 0
    n_closed = 0
    n_skipped = 0
    realized = 0.0

    # open-trade state
    e_idx = 0
    e_base = 0.0
    e_fill = 0.0
    qty = 0.0
    atr_e = 0.0
    lvl_dis = 0.0
    lvl_sl = 0.0
    lvl_tp = 0.0
    lvl_tr = 0.0
    extreme = 0.0
    c_spread = 0.0  # entry costs (USD)
    c_slip = 0.0
    c_comm = 0.0
    c_swap = 0.0  # swap so far (USD, + = charge)
    fav = 0.0  # best favourable price distance so far (>= 0)
    adv = 0.0  # worst adverse price distance so far (>= 0)

    for j in range(n):
        # ---------------------------------------------------------------- open of bar j
        exit_now = False
        x_reason = SIGNAL
        x_base = 0.0
        if in_trade and pend_exit:
            exit_now = True
            x_reason = pend_reason
            x_base = open_[j]
        elif in_trade:
            # gap through a stop (worse) or a target (better) at the open
            o = open_[j]
            best = -1.0e300
            hit = -1
            for which in range(3):
                if which == 0:
                    ok, lv, rs = use_sl, lvl_sl, STOP_LOSS
                elif which == 1:
                    ok, lv, rs = use_trail, lvl_tr, TRAILING_STOP
                else:
                    ok, lv, rs = True, lvl_dis, DISASTER_STOP
                if ok and d * (o - lv) <= 0.0 and d * lv > best:
                    best = d * lv
                    hit = rs
            if hit >= 0:
                exit_now = True
                x_reason = hit
                x_base = o
            elif use_tp and d * (o - lvl_tp) >= 0.0:
                exit_now = True
                x_reason = TAKE_PROFIT
                x_base = o
        if exit_now:
            x_fill = x_base - d * (half_spread[j] + slip_fixed[j] + slip_atr_frac * atr[j - 1])
            dist = d * (x_fill - e_base)
            if dist > fav:
                fav = dist
            if -dist > adv:
                adv = -dist
            realized, n_trades, n_closed = _close_trade(
                j, x_base, x_fill, x_reason, 0.0, d, e_idx, e_base, e_fill, qty, atr_e, c_spread,
                c_slip, c_comm, c_swap, fav, adv, half_spread, slip_fixed, slip_atr_frac, atr,
                c_code, c_p0, c_p1, c_p2, comm_in_quote, fx_close, point_value, realized,
                n_trades, n_closed, record, t_entry, t_exit, t_qty, t_entry_price,
                t_exit_price, t_gross, t_spread, t_slip, t_comm, t_swap, t_net, t_reason,
                t_mae, t_mfe, t_atr,
            )  # fmt: skip
            in_trade = False
            pend_exit = False
        do_entry = pend_entry and not in_trade
        pend_entry = False  # a scheduled entry is consumed at this open either way
        if do_entry:
            s = j - 1
            skip = False
            if sizing_mode == SIZE_RESEARCH:
                lots, skip = research_lots(
                    notional, open_[j] * fx_open[j], contract_size, volume_step, min_volume,
                    step_tol,
                )  # fmt: skip
                q = lots * contract_size
            elif sizing_mode == SIZE_CONTRACTS:
                q = contracts
            else:  # D-347: TradingView sizes at the signal close and floors to its step
                steps = notional / (close[s] * fx_close[s]) / parity_qty_step
                q = math.floor(steps * (1.0 + step_tol)) * parity_qty_step
            if skip or not q > 0.0:
                n_skipped += 1
            else:
                in_trade = True
                e_idx = j
                e_base = open_[j]
                qty = q
                atr_e = atr[s]
                cost_px = half_spread[j] + slip_fixed[j] + slip_atr_frac * atr[s]
                e_fill = e_base + d * cost_px
                f = fx_close[j]
                c_spread = qty * half_spread[j] * point_value * f
                c_slip = qty * (slip_fixed[j] + slip_atr_frac * atr[s]) * point_value * f
                comm = commission_kernel(c_code, c_p0, c_p1, c_p2, qty, e_fill)
                c_comm = comm * f if comm_in_quote else comm
                c_swap = 0.0
                fav = 0.0
                adv = 0.0
                # D-366: in parity mode with a tick size, TradingView turns the distance into
                # whole ticks (math.round, half away from zero) and measures it from the
                # ACTUAL FILL price. Research mode keeps the unrounded level from the raw open.
                if parity_tick > 0.0:
                    lvl_dis = e_fill - d * _ticks(disaster_atr * atr_e, parity_tick)
                    if use_sl:
                        lvl_sl = e_fill - d * _ticks(sl_atr * atr_e, parity_tick)
                    if use_tp:
                        lvl_tp = e_fill + d * _ticks(tp_atr * atr_e, parity_tick)
                    if use_trail:
                        lvl_tr = e_fill - d * _ticks(trail_atr * atr_e, parity_tick)
                        extreme = e_base
                else:
                    lvl_dis = e_base - d * disaster_atr * atr_e
                    if use_sl:
                        lvl_sl = e_base - d * sl_atr * atr_e
                    if use_tp:
                        lvl_tp = e_base + d * tp_atr * atr_e
                    if use_trail:
                        lvl_tr = e_base - d * trail_atr * atr_e
                        extreme = e_base
        # ---------------------------------------------------------------- intrabar
        if in_trade:
            best = -1.0e300
            stop_hit = -1
            stop_lv = 0.0
            adverse = low[j] if d > 0 else high[j]
            for which in range(3):
                if which == 0:
                    ok, lv, rs = use_sl, lvl_sl, STOP_LOSS
                elif which == 1:
                    ok, lv, rs = use_trail, lvl_tr, TRAILING_STOP
                else:
                    ok, lv, rs = True, lvl_dis, DISASTER_STOP
                if ok and d * (adverse - lv) <= 0.0 and d * lv > best:
                    best = d * lv
                    stop_hit = rs
                    stop_lv = lv
            favourable = high[j] if d > 0 else low[j]
            tp_hit = use_tp and d * (favourable - lvl_tp) >= 0.0
            take = -1
            if stop_hit >= 0 and tp_hit:
                if intrabar_mode == MODE_TRADINGVIEW:
                    up = high[j] - open_[j]
                    dn = open_[j] - low[j]
                    fav_first = up < dn if d > 0 else dn < up
                    take = TAKE_PROFIT if fav_first else stop_hit
                else:
                    take = stop_hit
            elif stop_hit >= 0:
                take = stop_hit
            elif tp_hit:
                take = TAKE_PROFIT
            if take >= 0:
                x_base = lvl_tp if take == TAKE_PROFIT else stop_lv
                x_fill = x_base - d * (half_spread[j] + slip_fixed[j] + slip_atr_frac * atr[j - 1])
                # excursions of the bars held at a close, plus the exit fill (D-349 (f))
                dist = d * (x_fill - e_base)
                if dist > fav:
                    fav = dist
                if -dist > adv:
                    adv = -dist
                extra_swap = 0.0
                if rollover[j] and intrabar_mode == MODE_PESSIMISTIC:
                    rate = swap_long[j] if d > 0 else swap_short[j]
                    if rate < 0.0:  # D-327: a charge, never a credit
                        days = 3.0 if triple[j] else 1.0
                        extra_swap = -rate * days * qty * close[j] * point_value * fx_close[j]
                realized, n_trades, n_closed = _close_trade(
                    j, x_base, x_fill, take, extra_swap, d, e_idx, e_base, e_fill, qty, atr_e,
                    c_spread, c_slip, c_comm, c_swap, fav, adv, half_spread, slip_fixed,
                    slip_atr_frac, atr, c_code, c_p0, c_p1, c_p2, comm_in_quote, fx_close,
                    point_value, realized, n_trades, n_closed, record, t_entry, t_exit, t_qty,
                    t_entry_price, t_exit_price, t_gross, t_spread, t_slip, t_comm, t_swap,
                    t_net, t_reason, t_mae, t_mfe, t_atr,
                )  # fmt: skip
                in_trade = False
        # ---------------------------------------------------------------- close of bar j
        open_pnl = 0.0
        if in_trade:
            up_d = d * ((high[j] if d > 0 else low[j]) - e_base)
            dn_d = -d * ((low[j] if d > 0 else high[j]) - e_base)
            if up_d > fav:
                fav = up_d
            if dn_d > adv:
                adv = dn_d
            if rollover[j]:
                rate = swap_long[j] if d > 0 else swap_short[j]
                days = 3.0 if triple[j] else 1.0
                c_swap -= rate * days * qty * close[j] * point_value * fx_close[j]
            if use_trail:
                if d > 0:
                    if high[j] > extreme:
                        extreme = high[j]
                elif low[j] < extreme:
                    extreme = low[j]
                cand = extreme - d * trail_atr * atr_e
                if d * (cand - lvl_tr) > 0.0:
                    lvl_tr = cand
            if exit_sig[j]:
                pend_exit = True
                pend_reason = SIGNAL
            elif time_exit_bars > 0 and j - e_idx + 1 >= time_exit_bars:
                pend_exit = True
                pend_reason = TIME_EXIT
            open_pnl = (
                d * qty * (close[j] - e_base) * point_value * fx_close[j]
                - c_spread - c_slip - c_comm - c_swap
            )  # fmt: skip
        # D-367: `entry_requires_flat` mirrors Pine's `strategy.position_size == 0` gate, which
        # refuses a re-entry on the close that schedules the exit. Default off = D-336.
        may_enter = (not in_trade) if entry_requires_flat else (not in_trade or pend_exit)
        if entry_sig[j] and j < n - 1 and atr[j] > 0.0 and may_enter:
            pend_entry = True
        equity[j] = initial_capital + realized + open_pnl
        in_pos[j] = in_trade
        realized_out[j] = realized
    open_end = 0.0
    if in_trade:
        open_end = equity[n - 1] - initial_capital - realized
    return n_trades, n_closed, open_end, n_skipped


@njit(cache=True)
def _close_trade(
    j, x_base, x_fill, reason, extra_swap, d, e_idx, e_base, e_fill, qty, atr_e, c_spread, c_slip,
    c_comm, c_swap, fav, adv, half_spread, slip_fixed, slip_atr_frac, atr, c_code, c_p0,
    c_p1, c_p2, comm_in_quote, fx_close, point_value, realized, n_trades, n_closed, record,
    t_entry, t_exit, t_qty, t_entry_price, t_exit_price, t_gross, t_spread, t_slip, t_comm,
    t_swap, t_net, t_reason, t_mae, t_mfe, t_atr,
):  # fmt: skip
    f = fx_close[j]
    ref = atr[j - 1] if j >= 1 else 0.0
    gross = d * qty * (x_base - e_base) * point_value * f
    sp = c_spread + qty * half_spread[j] * point_value * f
    sl = c_slip + qty * (slip_fixed[j] + slip_atr_frac * ref) * point_value * f
    comm_x = commission_kernel(c_code, c_p0, c_p1, c_p2, qty, x_fill)
    cm = c_comm + (comm_x * f if comm_in_quote else comm_x)
    sw = c_swap + extra_swap
    net = gross - (sp + sl + cm + sw)
    if record:
        k = n_trades
        t_entry[k] = e_idx
        t_exit[k] = j
        t_qty[k] = qty
        t_entry_price[k] = e_fill
        t_exit_price[k] = x_fill
        t_gross[k] = gross
        t_spread[k] = sp
        t_slip[k] = sl
        t_comm[k] = cm
        t_swap[k] = sw
        t_net[k] = net
        t_reason[k] = reason
        t_mae[k] = adv * qty * point_value * f
        t_mfe[k] = fav * qty * point_value * f
        t_atr[k] = atr_e
    return realized + net, n_trades + 1, n_closed + 1


@njit(cache=True)
def simulate_one(
    open_, high, low, close, atr, entry_sig, exit_sig, direction,
    time_exit_bars, sl_atr, tp_atr, trail_atr, disaster_atr,
    half_spread, slip_fixed, slip_atr_frac, swap_long, swap_short, rollover, triple,
    c_code, c_p0, c_p1, c_p2, comm_in_quote,
    fx_open, fx_close, sizing_mode, notional, contracts, point_value,
    contract_size, volume_step, min_volume, parity_qty_step, step_tol,
    initial_capital, intrabar_mode, parity_tick, entry_requires_flat,
):  # fmt: skip
    """One run with its trade list. Returns (trade arrays..., equity, in_position, realized,
    n_trades, open_pnl_end, n_skipped_min_volume)."""
    n = open_.shape[0]
    t_entry = np.zeros(n, np.int64)
    t_exit = np.zeros(n, np.int64)
    t_reason = np.zeros(n, np.int64)
    t_qty = np.zeros(n)
    t_entry_price = np.zeros(n)
    t_exit_price = np.zeros(n)
    t_gross = np.zeros(n)
    t_spread = np.zeros(n)
    t_slip = np.zeros(n)
    t_comm = np.zeros(n)
    t_swap = np.zeros(n)
    t_net = np.zeros(n)
    t_mae = np.zeros(n)
    t_mfe = np.zeros(n)
    t_atr = np.zeros(n)
    equity = np.zeros(n)
    in_pos = np.zeros(n, np.bool_)
    realized = np.zeros(n)
    nt, _nc, open_end, n_skip = _core(
        open_, high, low, close, atr, entry_sig, exit_sig, direction,
        time_exit_bars, sl_atr, tp_atr, trail_atr, disaster_atr,
        half_spread, slip_fixed, slip_atr_frac, swap_long, swap_short, rollover, triple,
        c_code, c_p0, c_p1, c_p2, comm_in_quote,
        fx_open, fx_close, sizing_mode, notional, contracts, point_value,
        contract_size, volume_step, min_volume, parity_qty_step, step_tol,
        initial_capital, intrabar_mode, parity_tick, entry_requires_flat, True,
        t_entry, t_exit, t_qty, t_entry_price, t_exit_price, t_gross, t_spread, t_slip,
        t_comm, t_swap, t_net, t_reason, t_mae, t_mfe, t_atr,
        equity, in_pos, realized,
    )  # fmt: skip
    return (
        t_entry[:nt], t_exit[:nt], t_qty[:nt], t_entry_price[:nt], t_exit_price[:nt],
        t_gross[:nt], t_spread[:nt], t_slip[:nt], t_comm[:nt], t_swap[:nt], t_net[:nt],
        t_reason[:nt], t_mae[:nt], t_mfe[:nt], t_atr[:nt],
        equity, in_pos, realized, nt, open_end, n_skip,
    )  # fmt: skip


@njit(cache=True, parallel=True)
def simulate_grid_kernel(
    open_, high, low, close, atr, entry_mat, exit_mat, direction,
    time_exit_bars, sl_atr, tp_atr, trail_atr, disaster_atr,
    half_spread, slip_fixed, slip_atr_frac, swap_long, swap_short, rollover, triple,
    c_code, c_p0, c_p1, c_p2, comm_in_quote,
    fx_open, fx_close, sizing_mode, notional, contracts, point_value,
    contract_size, volume_step, min_volume, parity_qty_step, step_tol,
    initial_capital, intrabar_mode, parity_tick, entry_requires_flat,
):  # fmt: skip
    """Configurations = columns of ``entry_mat``/``exit_mat`` (``n x k``) and entries of the
    per-configuration exit parameter arrays (length ``k``). Returns ``equity (k x n)``,
    ``in_position (k x n)``, ``n_closed_trades (k)``, ``n_skipped_min_volume (k)``; no trade
    lists per cell (CLAUDE.md "Do not")."""
    n = open_.shape[0]
    k = entry_mat.shape[1]
    equity = np.zeros((k, n))
    in_pos = np.zeros((k, n), np.bool_)
    n_closed = np.zeros(k, np.int64)
    n_skip = np.zeros(k, np.int64)
    for c in prange(k):  # type: ignore[attr-defined]
        dummy_i = np.zeros(1, np.int64)
        dummy_f = np.zeros(1)
        realized = np.zeros(n)
        ent = np.ascontiguousarray(entry_mat[:, c])
        ext = np.ascontiguousarray(exit_mat[:, c])
        eq = np.zeros(n)
        ip = np.zeros(n, np.bool_)
        _nt, nc, _oe, ns = _core(
            open_, high, low, close, atr, ent, ext, direction,
            time_exit_bars[c], sl_atr[c], tp_atr[c], trail_atr[c], disaster_atr,
            half_spread, slip_fixed, slip_atr_frac, swap_long, swap_short, rollover, triple,
            c_code, c_p0, c_p1, c_p2, comm_in_quote,
            fx_open, fx_close, sizing_mode, notional, contracts, point_value,
            contract_size, volume_step, min_volume, parity_qty_step, step_tol,
            initial_capital, intrabar_mode, parity_tick, entry_requires_flat, False,
            dummy_i, dummy_i, dummy_f, dummy_f, dummy_f, dummy_f, dummy_f, dummy_f,
            dummy_f, dummy_f, dummy_f, dummy_i, dummy_f, dummy_f, dummy_f,
            eq, ip, realized,
        )  # fmt: skip
        equity[c, :] = eq
        in_pos[c, :] = ip
        n_closed[c] = nc
        n_skip[c] = ns
    return equity, in_pos, n_closed, n_skip
