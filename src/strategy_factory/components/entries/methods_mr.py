"""Stage-2 mean-reversion methods (T13 §4.1, §4.2; F-2.1; D-622, D-626 ... D-634).

A **method** is an entry rule with free parameters (D-622); stage 2 screens each one over its
coarse grid (2 to 4 values per parameter, <= 64 cells, D-630) with stage 1's fixed exits. The
library is the spec's MR library plus the user's own suite
(``tools/tradingview/user_mr_suite.pine``), deduplicated into parameterised families (D-627):
no two methods produce the same signals (guarded by a test). ``#n`` in a docstring is the
number of the rule in the user's script.

**Mirror rule everywhere (D-626, D-632):** the short signal is the long rule on
``Bars.mirrored()`` (``p -> -p``). The script's own shorts are **not** reproduced where they
differ (#2's ``> 140`` is not the mirror of ``< 20``; #18's short threshold is a slip in the
script). Ratio rules (#6, #7, #9, #10) are written in the ``|ref|`` form,
``x < ref - f * |ref|``, which is ``x < ref * (1 - f)`` for positive prices and mirrors exactly
to ``x > ref * (1 + f)`` -- the literal ratio form is not translation-equivariant and its naive
mirror fires on ~80 % of bars (T13 plan §4).

Every method declares :meth:`warmup`: the first bar index at which it can signal for given
parameters (the random baseline draws signal bars only from there on, D-615). A test asserts
no method ever signals before it.

Grids are the plan's measured grids (D-631; ``docs/tasks/T13_plan.md`` §2-§3). Fixed
constants of a standard definition (MACD 12/26/9, Connors' streak 2 and rank 100, the stochastic
smoothing 3, the ATR lengths of the user's rules) are class constants, like stage 1's MACD.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

import numpy as np

from strategy_factory.components import indicators as ind
from strategy_factory.components.base import (
    Bars,
    BoolArray,
    FloatArray,
    ParamValue,
)
from strategy_factory.components.entries.method_base import (
    Method,
    choice_param,
    float_param,
    float_value,
    int_param,
    int_value,
    prev,
)
from strategy_factory.components.registry import register


# ------------------------------------------------------------------------------ helpers
def run_of(cond: BoolArray, count: int) -> BoolArray:
    """``cond`` true on this bar and on the ``count - 1`` bars before it."""
    c = np.asarray(cond, dtype=np.bool_)
    out = c.copy()
    for j in range(1, count):
        shifted = np.zeros_like(c)
        shifted[j:] = c[:-j]
        out &= shifted
    return out


def falling_run(x: FloatArray, count: int) -> BoolArray:
    """``x < x[1] < ... < x[count]``: ``count`` consecutive falls."""
    with np.errstate(invalid="ignore"):
        return run_of(x < prev(x), count)


def rising_run(x: FloatArray, count: int) -> BoolArray:
    with np.errstate(invalid="ignore"):
        return run_of(x > prev(x), count)


def below_by(x: FloatArray, ref: FloatArray, frac: float) -> BoolArray:
    """``x < ref * (1 - frac)`` for positive prices, as ``x < ref - frac * |ref|`` so the
    mirror rule is exact (D-632)."""
    with np.errstate(invalid="ignore"):
        return x < ref - frac * np.abs(ref)


def rolling_sum(x: FloatArray, m: int) -> FloatArray:
    """Sum of the last ``m`` values, current included; NaN until ``m`` values exist."""
    out = np.full(x.shape[0], np.nan)
    if m <= x.shape[0]:
        out[m - 1 :] = np.convolve(x, np.ones(m), mode="valid")
    return out


def ibs_pct(b: Bars) -> FloatArray:
    """IBS on the script's 0..100 scale; NaN when ``high == low``."""
    return ind.ibs(b.high, b.low, b.close) * 100.0


def macd_hist(b: Bars) -> FloatArray:
    return ind.macd(b.close, MACD_FAST, MACD_SLOW, MACD_SIGNAL).hist


def candle_total(b: Bars) -> FloatArray:
    """The script's ``totalScore = selfScore + coScore`` (lines 329-331).

    ``selfScore`` places the close in fifths of the bar's range (+2 top ... -2 bottom);
    ``coScore`` places it against the previous bar (+3 above its high, +2 upper third, 0 middle,
    -2 above its low, -3 below it). Bar 0 has no previous bar: NaN here, where the script scores
    it -3 through Pine's ``na`` comparisons (one bar at the start of the series).
    """
    c, h, lo = b.close, b.high, b.low
    h1, l1 = prev(h), prev(lo)
    with np.errstate(invalid="ignore"):
        self_ = np.select(
            [
                5 * c > 4 * h + lo,
                5 * c > 3 * h + 2 * lo,
                5 * c > 2 * h + 3 * lo,
                5 * c > h + 4 * lo,
            ],
            [2.0, 1.0, 0.0, -1.0],
            -2.0,
        )
        co = np.select(
            [c > h1, 3 * c > 2 * h1 + l1, 3 * c > h1 + 2 * l1, c > l1], [3.0, 2.0, 0.0, -2.0], -3.0
        )
    total = self_ + co
    total[np.isnan(h1)] = np.nan
    return np.asarray(total, dtype=np.float64)


def williams_pct(b: Bars, n: int) -> FloatArray:
    """The script's ``WilliamsPR(n)``: ``100 * (close - lowest low) / (highest high - lowest
    low)``, i.e. ``ta.wpr + 100`` (0..100)."""
    return ind.williams_r(b.high, b.low, b.close, n) + 100.0


def williams_latched(w: FloatArray, higher_high: BoolArray, t: float) -> BoolArray:
    """D-633 ``latched``: %R < t arms a trigger, the first bar with ``high > high[1]`` (the arming
    bar included) fires it and disarms it, %R > 100 - t disarms it. Causal by construction."""
    n = w.shape[0]
    out = np.zeros(n, dtype=np.bool_)
    armed = False
    for i in range(n):
        if w[i] < t:
            armed = True
        if armed and higher_high[i]:
            out[i] = True
            armed = False
        if w[i] > 100.0 - t:
            armed = False
    return out


MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
#: first bar with a MACD histogram: the slow EMA at ``slow - 1``, the signal EMA ``signal - 1``
#: bars later
MACD_HIST_FIRST = MACD_SLOW - 1 + MACD_SIGNAL - 1


class MrMethod(Method):
    """A stage-2 mean-reversion method."""

    edge_type: ClassVar[str] = "MR"


# ------------------------------------------------------------------------------ methods
@register
class MrIbs(MrMethod):
    """#0 and stage-1 IBS: IBS < t (0..100) on each of the last k bars."""

    name = "mr_ibs"
    trigger = "state"
    params = (
        float_param("t", 30.0, (15.0, 20.0, 30.0, 40.0), 5.0, 50.0, 1.0),
        int_param("k", 1, (1, 2, 3), 1, 5),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        with np.errstate(invalid="ignore"):
            return run_of(ibs_pct(bars) < float_value(params, "t"), int_value(params, "k"))

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "k") - 1


@register
class MrRsi(MrMethod):
    """#1, #19 and the stage-1 RSI probes: RSI(n) <= t (the script's ``<=``)."""

    name = "mr_rsi"
    trigger = "state"
    params = (
        int_param("n", 2, (2, 3, 5, 7), 2, 14),
        float_param("t", 20.0, (15.0, 20.0, 30.0, 35.0), 5.0, 45.0, 1.0),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        with np.errstate(invalid="ignore"):
            return ind.rsi(bars.close, int_value(params, "n")) <= float_value(params, "t")

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "n")


@register
class MrRsiSum(MrMethod):
    """#2 = cumulative RSI: the sum of RSI(n) over the last m bars < m * level.

    The script's rule is n 2, m 2, level 10 (``rsi2 + rsi2[1] < 20``). Its short, ``> 140``, is
    **not** the mirror; the mirror of ``< 20`` is ``> 180`` (D-632).
    """

    name = "mr_rsi_sum"
    trigger = "state"
    params = (
        int_param("n", 2, (2, 3, 4, 5), 2, 14),
        int_param("m", 2, (2, 3), 2, 5),
        float_param("level", 10.0, (15.0, 20.0, 25.0, 30.0), 5.0, 45.0, 1.0),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        m = int_value(params, "m")
        total = rolling_sum(ind.rsi(bars.close, int_value(params, "n")), m)
        with np.errstate(invalid="ignore"):
            return total < m * float_value(params, "level")

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "n") + int_value(params, "m") - 1


def connors_rsi_mirrorable(
    close: FloatArray, rsi_len: int, streak_len: int, rank_len: int
) -> FloatArray:
    """Connors RSI with its one-bar ROC written ``100 * (c - c[1]) / |c[1]|`` (D-632).

    For positive prices this **is** :func:`ind.connors_rsi` (a test asserts equality). The
    textbook ``(c - c[1]) / c[1]`` is a ratio: under ``p -> -p`` it keeps its sign, so the
    percent-rank third of the score would not mirror and the short would almost never fire
    (found by the engine-truncation gate's vacuity check). With ``|c[1]|`` the mirror is exact.
    """
    prev_c = prev(close)
    with np.errstate(invalid="ignore", divide="ignore"):
        roc1 = 100.0 * (close - prev_c) / np.abs(prev_c)
    a = ind.rsi(close, rsi_len)
    b = ind.rsi(ind.updown_streak(close), streak_len)
    r = ind.percent_rank(roc1, rank_len)
    return np.asarray((a + b + r) / 3.0, dtype=np.float64)


@register
class MrConnorsRsi(MrMethod):
    """F-2.1 Connors RSI: CRSI(rsi_len, 2, 100) < t (streak length and rank length fixed); the
    one-bar ROC in the ``|ref|`` form so the mirror is exact (see
    :func:`connors_rsi_mirrorable`)."""

    name = "mr_connors_rsi"
    trigger = "state"
    streak_length: ClassVar[int] = 2
    rank_length: ClassVar[int] = 100
    params = (
        int_param("rsi_len", 3, (2, 3, 4, 5), 2, 14),
        float_param("t", 20.0, (15.0, 20.0, 25.0, 30.0), 5.0, 45.0, 1.0),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        crsi = connors_rsi_mirrorable(
            bars.close, int_value(params, "rsi_len"), cls.streak_length, cls.rank_length
        )
        with np.errstate(invalid="ignore"):
            return crsi < float_value(params, "t")

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        # the percent rank of the one-bar return needs rank_length previous values
        return max(cls.rank_length, int_value(params, "rsi_len"), cls.streak_length + 1)


@register
class MrDownCloses(MrMethod):
    """#4 and stage-1 ``three_down_closes``: k consecutive lower closes."""

    name = "mr_down_closes"
    trigger = "state"
    params = (int_param("k", 3, (1, 2, 3, 4), 1, 8),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        return falling_run(bars.close, int_value(params, "k"))

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "k")


@register
class MrLowerLows(MrMethod):
    """#3: k consecutive lower lows (the script's ``Lower Low 3`` is k 3)."""

    name = "mr_lower_lows"
    trigger = "state"
    params = (int_param("k", 3, (1, 2, 3, 4), 1, 8),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        return falling_run(bars.low, int_value(params, "k"))

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "k")


@register
class MrNDayLow(MrMethod):
    """#5, F-2.1 N-day low, stage-1 ``donchian20_new_low`` and ``lowest_close_7``: the close
    below the lowest ``source`` of the previous n bars.

    ``source`` low is the script (``ta.lowest(n)`` defaults to the low) and the stage-1
    Donchian probe; close is the stage-1 closing-low form: one method, two values (D-634).
    """

    name = "mr_n_day_low"
    trigger = "event"
    params = (
        int_param("n", 5, (3, 5, 10, 20), 2, 50),
        choice_param("source", "low", ("low", "close")),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        src = bars.low if params["source"] == "low" else bars.close
        with np.errstate(invalid="ignore"):
            return bars.close < prev(ind.lowest(src, int_value(params, "n")))

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "n")


@register
class MrDailyDrop(MrMethod):
    """#6 (ATR expanding) and #7 (plain; the script's "Small ATR" condition is commented out):
    close below the previous close by d %, optionally with ATR(5) > ATR(10).

    Written ``close < close[1] - d * |close[1]|`` (D-632). The script's #6 writes
    ``close * 1.01 < close[1]`` (``close[1] / 1.01``); the two differ on ~0.5 % of signals.
    """

    name = "mr_daily_drop"
    trigger = "state"
    atr_fast: ClassVar[int] = 5
    atr_slow: ClassVar[int] = 10
    params = (
        float_param("d", 1.0, (0.5, 1.0, 2.0, 3.0), 0.1, 10.0, 0.1),
        choice_param("atr_expanding", "off", ("off", "on")),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        c = bars.close
        sig = below_by(c, prev(c), float_value(params, "d") / 100.0)
        if params["atr_expanding"] == "on":
            fast = ind.atr(bars.high, bars.low, c, cls.atr_fast)
            slow = ind.atr(bars.high, bars.low, c, cls.atr_slow)
            with np.errstate(invalid="ignore"):
                sig = sig & (fast > slow)
        return sig

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return cls.atr_slow - 1 if params["atr_expanding"] == "on" else 1


@register
class MrMaDistancePct(MrMethod):
    """#9 and F-2.1 distance from a moving average, in percent: close below EMA(n) by p %.

    Written ``close < ema - p * |ema|`` (D-632). Split from the ATR form (D-630).
    """

    name = "mr_ma_distance_pct"
    trigger = "state"
    params = (
        int_param("n", 5, (5, 10, 20, 50), 2, 200),
        float_param("p", 1.0, (0.5, 1.0, 2.0, 3.0), 0.1, 10.0, 0.1),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        ema = ind.ema(bars.close, int_value(params, "n"))
        return below_by(bars.close, ema, float_value(params, "p") / 100.0)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "n") - 1


@register
class MrMaDistanceAtr(MrMethod):
    """#8 and F-2.1 distance from a moving average, in ATR: ``close + a * ATR(5) < EMA(n)``.
    Split from the percent form (D-630)."""

    name = "mr_ma_distance_atr"
    trigger = "state"
    atr_length: ClassVar[int] = 5
    params = (
        int_param("n", 5, (5, 10, 20, 50), 2, 200),
        float_param("a", 0.5, (0.25, 0.5, 1.0, 1.5), 0.05, 5.0, 0.05),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        ema = ind.ema(bars.close, int_value(params, "n"))
        atr = ind.atr(bars.high, bars.low, bars.close, cls.atr_length)
        with np.errstate(invalid="ignore"):
            return bars.close + float_value(params, "a") * atr < ema

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return max(int_value(params, "n") - 1, cls.atr_length - 1)


@register
class MrEmaSlopeDrop(MrMethod):
    """#10: EMA(n) fell by more than p % in one bar, written
    ``ema < ema[1] - p * |ema[1]|`` (D-632)."""

    name = "mr_ema_slope_drop"
    trigger = "state"
    params = (
        int_param("n", 5, (3, 5, 8, 10), 2, 50),
        float_param("p", 0.5, (0.25, 0.5, 0.75, 1.0), 0.05, 5.0, 0.05),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        ema = ind.ema(bars.close, int_value(params, "n"))
        return below_by(ema, prev(ema), float_value(params, "p") / 100.0)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "n")


@register
class MrIbsAfterNewHigh(MrMethod):
    """#14 (a pullback inside strength): the high above the highest high of the previous n
    bars, and IBS < t (0..100)."""

    name = "mr_ibs_after_new_high"
    trigger = "state"
    params = (
        int_param("n", 10, (3, 5, 10, 20), 2, 100),
        float_param("t", 15.0, (15.0, 20.0, 25.0, 30.0), 5.0, 50.0, 1.0),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        with np.errstate(invalid="ignore"):
            new_high = bars.high > prev(ind.highest(bars.high, int_value(params, "n")))
            return new_high & (ibs_pct(bars) < float_value(params, "t"))

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "n")


@register
class MrMacdHistFalling(MrMethod):
    """#17: the MACD(12, 26, 9) histogram fell k bars in a row, is below 0, and
    close < close[1] (the script's k is 4)."""

    name = "mr_macd_hist_falling"
    trigger = "state"
    params = (int_param("k", 4, (2, 3, 4, 5), 1, 10),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        h = macd_hist(bars)
        with np.errstate(invalid="ignore"):
            return (
                falling_run(h, int_value(params, "k")) & (h < 0) & (bars.close < prev(bars.close))
            )

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return MACD_HIST_FIRST + int_value(params, "k")


@register
class MrMacdHistTurn(MrMethod):
    """#20: the MACD(12, 26, 9) histogram rose k bars in a row while below 0 (the script's k
    is 2). Not the stage-1 trough probe: that is a minimum, this is a rise."""

    name = "mr_macd_hist_turn"
    trigger = "state"
    params = (int_param("k", 2, (1, 2, 3, 4), 1, 10),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        h = macd_hist(bars)
        with np.errstate(invalid="ignore"):
            return rising_run(h, int_value(params, "k")) & (h < 0)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return MACD_HIST_FIRST + int_value(params, "k")


@register
class MrMacdHistTrough(MrMethod):
    """Stage-1 ``macd_hist_trough_5``: the MACD(12, 26, 9) histogram at its lowest value of the
    last w bars, current bar included."""

    name = "mr_macd_hist_trough"
    trigger = "state"
    params = (int_param("w", 5, (3, 5, 7, 10), 2, 30),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        h = macd_hist(bars)
        with np.errstate(invalid="ignore"):
            return h <= ind.lowest(h, int_value(params, "w"))

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return MACD_HIST_FIRST + int_value(params, "w") - 1


@register
class MrCandleScore(MrMethod):
    """#18: the script's candle score summed over n bars <= n * level; ``rising`` also needs
    the sum above its previous value (#18 "Rising").

    The script's rule is n 3, threshold -7 (``level`` -7/3 per bar). Its short uses the **same**
    threshold (``>= -7``) and fires on ~88 % of daily bars: a slip in the script; the short here
    is the mirror, ``>= +7`` (D-632).
    """

    name = "mr_candle_score"
    trigger = "state"
    params = (
        int_param("n", 3, (2, 3, 4, 5), 1, 20),
        float_param("level", -2.5, (-2.5, -2.0, -1.5, -1.0), -5.0, 5.0, 0.25),
        choice_param("mode", "level", ("level", "rising")),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        n = int_value(params, "n")
        total = rolling_sum(candle_total(bars), n)
        with np.errstate(invalid="ignore"):
            sig = total <= n * float_value(params, "level")
            if params["mode"] == "rising":
                sig = sig & (total > prev(total))
        return np.asarray(sig, dtype=np.bool_)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "n") + (1 if params["mode"] == "rising" else 0)


@register
class MrWilliamsConfirm(MrMethod):
    """#22 and F-2.1 Williams %R: %R(n) (0..100) < t, with a confirmation choice.

    * ``off``: %R < t alone (F-2.1's Williams %R);
    * ``same_bar``: %R < t **and** ``high > high[1]`` on the same bar -- what the user's
      backtests ran (the script's trigger has no ``var`` and resets every bar, D-633);
    * ``latched``: %R < t arms a trigger that the first later (or the same) bar with
      ``high > high[1]`` fires; %R > 100 - t disarms it -- what the rule was meant to be.

    The script has no short; the short here is the mirror (D-632).
    """

    name = "mr_williams_confirm"
    trigger = "state"
    params = (
        int_param("n", 5, (5, 10, 14, 20), 2, 50),
        float_param("t", 20.0, (5.0, 10.0, 20.0, 30.0), 1.0, 45.0, 1.0),
        choice_param("confirm", "same_bar", ("off", "same_bar", "latched")),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        n, t = int_value(params, "n"), float_value(params, "t")
        w = williams_pct(bars, n)
        with np.errstate(invalid="ignore"):
            below = w < t
            higher_high = bars.high > prev(bars.high)
        confirm = params["confirm"]
        if confirm == "off":
            return below
        if confirm == "same_bar":
            return below & higher_high
        return williams_latched(w, higher_high, t)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        first = int_value(params, "n") - 1
        return first if params["confirm"] == "off" else max(first, 1)


@register
class MrZscore(MrMethod):
    """Stage-1 z-score probe (it replaces ``close_below_bb_lower``, the same rule, D-627):
    z(close, n) < -t."""

    name = "mr_zscore"
    trigger = "state"
    params = (
        int_param("n", 20, (10, 20, 30, 40), 5, 100),
        float_param("t", 1.5, (1.0, 1.25, 1.5, 2.0), 0.25, 4.0, 0.05),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        with np.errstate(invalid="ignore"):
            return ind.zscore(bars.close, int_value(params, "n")) < -float_value(params, "t")

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "n") - 1


@register
class MrStochasticK(MrMethod):
    """F-2.1 stochastic: the smoothed %K(n, 3) < t. Smoothed, so it is not the raw %R of
    ``mr_williams_confirm``."""

    name = "mr_stochastic_k"
    trigger = "state"
    k_smooth: ClassVar[int] = 3
    params = (
        int_param("n", 14, (5, 9, 14, 21), 2, 50),
        float_param("t", 20.0, (10.0, 15.0, 20.0, 30.0), 1.0, 45.0, 1.0),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        k = ind.stochastic(
            bars.high, bars.low, bars.close, int_value(params, "n"), cls.k_smooth, 3
        ).k
        with np.errstate(invalid="ignore"):
            return k < float_value(params, "t")

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "n") - 1 + cls.k_smooth - 1


@register
class MrKeltnerLower(MrMethod):
    """F-2.1 Keltner lower band: close below the lower Keltner band (n, mult)."""

    name = "mr_keltner_lower"
    trigger = "state"
    params = (
        int_param("n", 20, (10, 20, 30, 40), 5, 100),
        float_param("mult", 1.0, (0.5, 1.0, 1.5, 2.0), 0.25, 4.0, 0.05),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        kc = ind.keltner(
            bars.high, bars.low, bars.close, int_value(params, "n"), float_value(params, "mult")
        )
        with np.errstate(invalid="ignore"):
            return bars.close < kc.lower

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return int_value(params, "n")
