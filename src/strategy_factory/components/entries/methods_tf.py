"""Stage-2 trend-following methods (T13 §4.3; F-2.2; D-622, D-626, D-627, D-630, D-631, D-635).

The stage-1 TF probes parameterised (the two Donchian probes are one method), the spec's
additions (Keltner breakout, ADX/DI, Hull MA, KAMA, Parabolic SAR, Aroon) and two rules of the
user's script: ``tf_atr_band`` (#11) and ``tf_base_candle`` (#23). **Dual momentum is deferred
to P1 (D-635):** it needs the SPX aux series and cannot be mirrored.

Mirror rule everywhere (D-626, D-632); every indicator here is translation-equivariant or
difference-based, so ``Bars.mirrored`` gives the exact short (ROC is expressed as momentum, as
stage 1 does). The user's #11 has no short in the script; the short here is the mirror.
Every method declares :meth:`warmup` (see ``methods_mr``). Grids are the plan's (D-631).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

import numpy as np

from strategy_factory.components import indicators as ind
from strategy_factory.components.base import Bars, BoolArray, FloatArray, ParamValue
from strategy_factory.components.entries.methods_mr import (
    _float,
    _float_param,
    _int,
    _int_param,
    _Method,
    prev,
)
from strategy_factory.components.registry import register


def crossover(a: FloatArray, b: FloatArray) -> BoolArray:
    """Pine ``ta.crossover``: ``a > b`` now and ``a[1] <= b[1]``; False where anything is NaN."""
    with np.errstate(invalid="ignore"):
        return (a > b) & (prev(a) <= prev(b))


def turns_up(x: FloatArray) -> BoolArray:
    """``x`` rises after not rising: ``x > x[1]`` and ``x[1] <= x[2]``."""
    with np.errstate(invalid="ignore"):
        return (x > prev(x)) & (prev(x) <= prev(x, 2))


class _TfMethod(_Method):
    edge_type: ClassVar[str] = "TF"


@register
class TfMaSlope(_TfMethod):
    """Stage-1 ``ma50_slope_up``: the slope of SMA(n) turns positive."""

    name = "tf_ma_slope"
    trigger = "event"
    params = (_int_param("n", 50, (20, 50, 100, 200), 5, 250),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        slope = ind.sma_slope(bars.close, _int(params, "n"))
        with np.errstate(invalid="ignore"):
            return (slope > 0.0) & (prev(slope) <= 0.0)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return _int(params, "n") + 1


@register
class TfSmaCross(_TfMethod):
    """Stage-1 ``sma_cross_20_100``: SMA(fast) crosses above SMA(slow)."""

    name = "tf_sma_cross"
    trigger = "event"
    params = (
        _int_param("fast", 10, (5, 10, 15, 20), 2, 50),
        _int_param("slow", 50, (30, 50, 75, 100), 21, 300),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        c = bars.close
        return crossover(ind.sma(c, _int(params, "fast")), ind.sma(c, _int(params, "slow")))

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return max(_int(params, "fast"), _int(params, "slow"))


@register
class TfDonchianBreakout(_TfMethod):
    """Stage-1 ``donchian20_breakout`` and ``donchian55_breakout``, one method: the close
    above the highest high of the previous n bars."""

    name = "tf_donchian_breakout"
    trigger = "event"
    params = (_int_param("n", 20, (10, 20, 55, 100), 5, 200),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        with np.errstate(invalid="ignore"):
            return bars.close > prev(ind.highest(bars.high, _int(params, "n")))

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return _int(params, "n")


@register
class TfBbUpperCross(_TfMethod):
    """Stage-1 ``bb_upper_cross``: the close crosses above the upper Bollinger band."""

    name = "tf_bb_upper"
    trigger = "event"
    params = (
        _int_param("n", 20, (10, 20, 30, 40), 5, 100),
        _float_param("mult", 2.0, (1.0, 1.5, 2.0, 2.5), 0.5, 4.0, 0.1),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        bb = ind.bollinger(bars.close, _int(params, "n"), _float(params, "mult"))
        return crossover(bars.close, bb.upper)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return _int(params, "n")


@register
class TfSupertrendFlip(_TfMethod):
    """Stage-1 ``supertrend_flip``: Supertrend turns to an up-trend (TradingView -1 = up)."""

    name = "tf_supertrend"
    trigger = "event"
    params = (
        _int_param("atr", 10, (7, 10, 14, 20), 2, 50),
        _float_param("factor", 3.0, (2.0, 2.5, 3.0, 3.5), 1.0, 5.0, 0.1),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        d = ind.supertrend(
            bars.high, bars.low, bars.close, _float(params, "factor"), _int(params, "atr")
        ).direction
        return (d == -1.0) & (prev(d) == 1.0)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return _int(params, "atr")


@register
class TfIchimokuCloud(_TfMethod):
    """Stage-1 ``ichimoku_cloud``: the close above the cloud and tenkan > kijun (the cloud at
    bar i is the spans of ``base - 1`` bars earlier, as TradingView plots it)."""

    name = "tf_ichimoku"
    trigger = "state"
    params = (
        _int_param("conversion", 9, (7, 9, 12, 15), 2, 20),
        _int_param("base", 26, (22, 26, 30, 40), 21, 60),
        _int_param("span_b", 52, (44, 52, 60, 80), 21, 120),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        base = _int(params, "base")
        ich = ind.ichimoku(
            bars.high, bars.low, _int(params, "conversion"), base, _int(params, "span_b")
        )
        top = np.maximum(prev(ich.span_a_raw, base - 1), prev(ich.span_b_raw, base - 1))
        with np.errstate(invalid="ignore"):
            return (bars.close > top) & (ich.tenkan > ich.kijun)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return max(_int(params, "span_b"), _int(params, "conversion")) + _int(params, "base") - 2


@register
class TfMomentumCross(_TfMethod):
    """Stage-1 ``roc20_cross_zero``: momentum ``close - close[n]`` crosses above 0 (the sign of
    ROC for positive prices, and mirror-exact)."""

    name = "tf_momentum_cross"
    trigger = "event"
    params = (_int_param("n", 20, (10, 20, 40, 60), 2, 250),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        mom = ind.momentum(bars.close, _int(params, "n"))
        with np.errstate(invalid="ignore"):
            return (mom > 0.0) & (prev(mom) <= 0.0)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return _int(params, "n") + 1


@register
class TfKeltnerBreakout(_TfMethod):
    """F-2.2 Keltner breakout: the close crosses above the upper Keltner band (n, mult)."""

    name = "tf_keltner_breakout"
    trigger = "event"
    params = (
        _int_param("n", 20, (10, 20, 30, 40), 5, 100),
        _float_param("mult", 1.5, (0.75, 1.0, 1.5, 2.0), 0.25, 4.0, 0.05),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        kc = ind.keltner(bars.high, bars.low, bars.close, _int(params, "n"), _float(params, "mult"))
        return crossover(bars.close, kc.upper)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return _int(params, "n") + 1


@register
class TfAdxDi(_TfMethod):
    """F-2.2 ADX/DI: DI+ crosses above DI- while ADX(n) > t."""

    name = "tf_adx_di"
    trigger = "event"
    params = (
        _int_param("n", 10, (5, 7, 10, 14), 2, 50),
        _float_param("t", 20.0, (10.0, 15.0, 20.0, 25.0), 5.0, 50.0, 1.0),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        n = _int(params, "n")
        d = ind.dmi(bars.high, bars.low, bars.close, n, n)
        with np.errstate(invalid="ignore"):
            return crossover(d.plus, d.minus) & (d.adx > _float(params, "t"))

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return 2 * _int(params, "n") - 1  # ADX: the DI from bar n, their RMA n - 1 bars later


@register
class TfHmaTurn(_TfMethod):
    """F-2.2 Hull MA: HMA(n) turns up."""

    name = "tf_hma_turn"
    trigger = "event"
    params = (_int_param("n", 16, (9, 16, 25, 49), 4, 200),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        return turns_up(ind.hma(bars.close, _int(params, "n")))

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        n = _int(params, "n")
        return n - 1 + int(np.floor(np.sqrt(n))) - 1 + 2


@register
class TfKamaCross(_TfMethod):
    """F-2.2 KAMA: the close crosses above KAMA(n, 2, 30)."""

    name = "tf_kama_cross"
    trigger = "event"
    kama_fast: ClassVar[int] = 2
    kama_slow: ClassVar[int] = 30
    params = (_int_param("n", 10, (5, 10, 20, 30), 2, 100),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        k = ind.kama(bars.close, _int(params, "n"), cls.kama_fast, cls.kama_slow)
        return crossover(bars.close, k)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return _int(params, "n")  # KAMA is seeded at n - 1; the cross needs one value before


@register
class TfPsarFlip(_TfMethod):
    """F-2.2 Parabolic SAR: the SAR flips below the price (start = increment = step)."""

    name = "tf_psar_flip"
    trigger = "event"
    params = (
        _float_param("step", 0.02, (0.01, 0.02, 0.03, 0.04), 0.005, 0.1, 0.005),
        _float_param("maximum", 0.2, (0.1, 0.2, 0.3, 0.4), 0.05, 0.5, 0.05),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        step = _float(params, "step")
        s = ind.psar(bars.high, bars.low, bars.close, step, step, _float(params, "maximum"))
        with np.errstate(invalid="ignore"):
            return (s < bars.close) & (prev(s) > prev(bars.close))

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return 2


@register
class TfAroonCross(_TfMethod):
    """F-2.2 Aroon: Aroon up crosses above Aroon down."""

    name = "tf_aroon_cross"
    trigger = "event"
    params = (_int_param("n", 25, (10, 14, 25, 50), 2, 200),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        a = ind.aroon(bars.high, bars.low, _int(params, "n"))
        return crossover(a.up, a.down)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return _int(params, "n") + 1


@register
class TfAtrBand(_TfMethod):
    """#11 (SuperTrend-like): the close above the lowest low of n bars plus k * ATR(m). The
    script has no short (commented out); the short here is the mirror (D-632)."""

    name = "tf_atr_band"
    trigger = "state"
    params = (
        _int_param("n", 10, (5, 10, 20, 40), 2, 100),
        _float_param("k", 2.5, (1.5, 2.0, 2.5, 3.0), 0.5, 5.0, 0.1),
        _int_param("m", 25, (10, 14, 25, 50), 2, 100),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        atr = ind.atr(bars.high, bars.low, bars.close, _int(params, "m"))
        band = ind.lowest(bars.low, _int(params, "n")) + _float(params, "k") * atr
        with np.errstate(invalid="ignore"):
            return bars.close > band

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return max(_int(params, "n"), _int(params, "m")) - 1


def base_candle_direction(bars: Bars, frac: float) -> tuple[FloatArray, FloatArray]:
    """The script's BaseCandle state machine (lines 387-413) with a strong-close fraction
    ``frac`` (the script's is 1/3: ``3 * close > 2 * high + low``).

    Returns ``(direction, long_base)``: direction +1 / -1 per bar, ``long_base`` +1 / -1 on a
    base candle and 0 otherwise. The machine starts in the long direction on the first bar's
    range, as the script does.
    """
    o, h, lo, c = bars.open, bars.high, bars.low, bars.close
    n = len(bars)
    direction = np.zeros(n)
    long_base = np.zeros(n)
    if n == 0:
        return direction, long_base
    base_high, base_low, long_dir = h[0], lo[0], True
    for i in range(n):
        rng = h[i] - lo[i]
        strong_up = c[i] > h[i] - frac * rng
        strong_dn = c[i] < lo[i] + frac * rng
        lb = 0.0
        if long_dir and strong_up and c[i] > o[i] and h[i] > base_high:
            base_high, base_low, lb = h[i], lo[i], 1.0
        elif (not long_dir) and strong_dn and c[i] < o[i] and lo[i] < base_low:
            base_high, base_low, lb = h[i], lo[i], -1.0
        elif long_dir and strong_dn and c[i] < o[i] and c[i] < base_low:
            base_high, base_low, long_dir, lb = h[i], lo[i], False, -1.0
        elif (not long_dir) and strong_up and c[i] > o[i] and c[i] > base_high:
            base_high, base_low, long_dir, lb = h[i], lo[i], True, 1.0
        direction[i] = 1.0 if long_dir else -1.0
        long_base[i] = lb
    return direction, long_base


@register
class TfBaseCandle(_TfMethod):
    """#23 BaseCandle: the base-candle direction flips to long.

    The script has no parameter; ``frac`` (the strong-close fraction) is added so the method has
    a grid, with the script's 1/3 among its values (D-631). The mirror starts in the opposite
    state, which differs from the script only until the first flip.
    """

    name = "tf_base_candle"
    trigger = "event"
    params = (_float_param("frac", 1 / 3, (0.25, 1 / 3, 0.4, 0.5), 0.1, 0.5, 0.01),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        d, _ = base_candle_direction(bars, _float(params, "frac"))
        return (d == 1.0) & (prev(d) == -1.0)

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        return 1
