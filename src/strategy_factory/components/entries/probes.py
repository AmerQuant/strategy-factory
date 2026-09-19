"""Stage-1 probe entries (spec v1.2 stage 1 §1.2; F-1.1, F-1.2): signals only.

Each probe is a fixed-parameter entry rule tagged with its edge type and probe group. The
defaults are the spec's fixed probe parameters; stage 1 runs them at the defaults only. The
coarse grids exist because every :class:`ParamSpec` must declare one (F-0.4.1) — they are not
used by stage 1 (see the T07 review, open questions).

All probes follow the mirror rule: the short signal is the long rule on the mirrored series
(``Bars.mirrored``), e.g. "close below the lower band" becomes "close above the upper band".
Breakouts are close-based (spec addendum §1.6): the close is compared with the channel of the
*previous* bar. NaN (warm-up) never produces a signal.

``trigger`` classifies each rule: ``state`` probes (thresholds and level comparisons) are true
on every bar the condition holds; ``event`` probes (crossovers, channel breakouts, flips) mark
the bar a condition starts. A Donchian breakout compares with the prior bars' channel, so it
can repeat on consecutive bars when each bar makes a new extreme (each is a new breakout).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

import numpy as np

from strategy_factory.components import indicators as ind
from strategy_factory.components.base import (
    Bars,
    BoolArray,
    EntryComponent,
    FloatArray,
    ParamSpec,
    ParamValue,
    Trigger,
)
from strategy_factory.components.registry import register


def _prev(x: FloatArray, periods: int = 1) -> FloatArray:
    """``x[periods]`` in Pine notation (value ``periods >= 1`` bars ago; NaN before start)."""
    out = np.full(x.shape[0], np.nan)
    if 0 < periods < x.shape[0]:
        out[periods:] = x[:-periods]
    return out


def crossover(a: FloatArray, b: FloatArray) -> BoolArray:
    """Pine ``ta.crossover``: ``a > b`` now and ``a[1] <= b[1]``; False where anything is NaN."""
    return (a > b) & (_prev(a) <= _prev(b))


def _int(p: Mapping[str, ParamValue], key: str) -> int:
    return int(p[key])


def _float(p: Mapping[str, ParamValue], key: str) -> float:
    return float(p[key])


def _length(
    name: str, default: int, coarse: tuple[int, int, int, int], lo: int, hi: int
) -> ParamSpec:
    return ParamSpec(
        name=name, kind="int", default=default, min=lo, max=hi, coarse_values=coarse, fine_step=1
    )


def _threshold(
    name: str, default: float, coarse: tuple[float, ...], lo: float, hi: float, step: float
) -> ParamSpec:
    return ParamSpec(
        name=name,
        kind="float",
        default=default,
        min=lo,
        max=hi,
        coarse_values=coarse,
        fine_step=step,
    )


class _Probe(EntryComponent):
    edge_type: ClassVar[str]
    group: ClassVar[str | None]
    trigger: ClassVar[Trigger | None]


# ------------------------------------------------------------------------------ MR probes


class _RsiBelow(_Probe):
    edge_type = "MR"
    group = "oscillator"

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        return ind.rsi(bars.close, _int(params, "length")) < _float(params, "threshold")


@register
class MrRsi2Below10(_RsiBelow):
    """RSI(2) < 10 (short: RSI(2) > 90)."""

    name = "mr_rsi2_below_10"
    trigger = "state"
    params = (
        _length("length", 2, (2, 3, 4, 5), 2, 14),
        _threshold("threshold", 10.0, (5.0, 10.0, 15.0, 20.0), 1.0, 40.0, 1.0),
    )


@register
class MrRsi5Below30(_RsiBelow):
    """RSI(5) < 30 (short: RSI(5) > 70)."""

    name = "mr_rsi5_below_30"
    trigger = "state"
    params = (
        _length("length", 5, (3, 5, 7, 9), 2, 14),
        _threshold("threshold", 30.0, (20.0, 25.0, 30.0, 35.0), 1.0, 45.0, 1.0),
    )


@register
class MrIbsBelow(_Probe):
    """IBS < 0.2 (short: IBS > 0.8). Bars with high == low have no IBS and no signal."""

    name = "mr_ibs_below_0_2"
    trigger = "state"
    edge_type = "MR"
    group = "oscillator"
    params = (_threshold("threshold", 0.2, (0.1, 0.2, 0.3, 0.4), 0.05, 0.5, 0.05),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        return ind.ibs(bars.high, bars.low, bars.close) < _float(params, "threshold")


@register
class MrCloseBelowBollinger(_Probe):
    """Close below the lower Bollinger band (20, 2) (short: close above the upper band)."""

    name = "mr_close_below_bb_lower"
    trigger = "state"
    edge_type = "MR"
    group = "band_channel"
    params = (
        _length("length", 20, (10, 20, 30, 40), 5, 100),
        _threshold("mult", 2.0, (1.5, 2.0, 2.5, 3.0), 0.5, 4.0, 0.1),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        bb = ind.bollinger(bars.close, _int(params, "length"), _float(params, "mult"))
        return bars.close < bb.lower


@register
class MrDonchianNewLow(_Probe):
    """Close below the previous bar's Donchian-20 low, i.e. below the lowest low of the prior
    20 bars (short: close above the highest high of the prior 20 bars)."""

    name = "mr_donchian20_new_low"
    trigger = "event"
    edge_type = "MR"
    group = "band_channel"
    params = (_length("length", 20, (10, 20, 30, 40), 5, 100),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        return bars.close < _prev(ind.lowest(bars.low, _int(params, "length")))


@register
class MrZscoreBelow(_Probe):
    """Z-score of close vs its 20-bar SMA < -2 (short: > +2). ``threshold`` is the magnitude."""

    name = "mr_zscore_below_minus_2"
    trigger = "state"
    edge_type = "MR"
    group = "band_channel"
    params = (
        _length("length", 20, (10, 20, 30, 40), 5, 100),
        _threshold("threshold", 2.0, (1.5, 2.0, 2.5, 3.0), 0.5, 4.0, 0.1),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        return ind.zscore(bars.close, _int(params, "length")) < -_float(params, "threshold")


@register
class MrLowestClose(_Probe):
    """Close is the lowest close of the last 7 bars, current bar included (short: highest)."""

    name = "mr_lowest_close_7"
    trigger = "state"
    edge_type = "MR"
    group = "band_channel"
    params = (_length("length", 7, (5, 7, 10, 14), 2, 50),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        return bars.close <= ind.lowest(bars.close, _int(params, "length"))


@register
class MrDownCloses(_Probe):
    """Three consecutive lower closes: ``close < close[1]`` on each of the last 3 bars
    (short: three consecutive higher closes)."""

    name = "mr_three_down_closes"
    trigger = "state"
    edge_type = "MR"
    group = "sequence"
    params = (_length("count", 3, (2, 3, 4, 5), 1, 10),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        c = bars.close
        down = c < _prev(c)
        out = down.copy()
        for k in range(1, _int(params, "count")):
            shifted = np.zeros_like(down)
            if k < down.shape[0]:
                shifted[k:] = down[:-k]
            out &= shifted
        return out


@register
class MrMacdHistTrough(_Probe):
    """MACD(12, 26, 9) histogram at its lowest value of the last 5 bars, current bar included
    (short: at its highest). MACD settings are the standard definition; ``window`` is the
    probe parameter."""

    name = "mr_macd_hist_trough_5"
    trigger = "state"
    edge_type = "MR"
    group = "momentum"
    params = (_length("window", 5, (3, 5, 7, 10), 2, 30),)
    macd_fast: ClassVar[int] = 12
    macd_slow: ClassVar[int] = 26
    macd_signal: ClassVar[int] = 9

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        hist = ind.macd(bars.close, cls.macd_fast, cls.macd_slow, cls.macd_signal).hist
        return hist <= ind.lowest(hist, _int(params, "window"))


# ------------------------------------------------------------------------------ TF probes


@register
class TfMaSlopeUp(_Probe):
    """Slope of SMA(50) turns up: ``slope > 0`` and ``slope[1] <= 0`` (short: turns down)."""

    name = "tf_ma50_slope_up"
    trigger = "event"
    edge_type = "TF"
    group = "ma"
    params = (_length("length", 50, (20, 50, 100, 200), 5, 250),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        slope = ind.sma_slope(bars.close, _int(params, "length"))
        return (slope > 0.0) & (_prev(slope) <= 0.0)


@register
class TfSmaCross(_Probe):
    """SMA(20) crosses above SMA(100) (short: crosses below)."""

    name = "tf_sma_cross_20_100"
    trigger = "event"
    edge_type = "TF"
    group = "ma"
    params = (
        _length("fast", 20, (10, 20, 30, 40), 2, 50),
        _length("slow", 100, (60, 100, 150, 200), 51, 300),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        c = bars.close
        return crossover(ind.sma(c, _int(params, "fast")), ind.sma(c, _int(params, "slow")))


class _DonchianBreakout(_Probe):
    edge_type = "TF"
    group = "channel_breakout"

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        return bars.close > _prev(ind.highest(bars.high, _int(params, "length")))


@register
class TfDonchian20Breakout(_DonchianBreakout):
    """Close above the highest high of the prior 20 bars (short: below the lowest low)."""

    name = "tf_donchian20_breakout"
    trigger = "event"
    params = (_length("length", 20, (10, 20, 30, 40), 5, 100),)


@register
class TfDonchian55Breakout(_DonchianBreakout):
    """Close above the highest high of the prior 55 bars (short: below the lowest low)."""

    name = "tf_donchian55_breakout"
    trigger = "event"
    params = (_length("length", 55, (40, 55, 70, 100), 20, 200),)


@register
class TfBbUpperCross(_Probe):
    """Close crosses above the upper Bollinger band (20, 2): ``close > upper`` and
    ``close[1] <= upper[1]`` (short: close crosses below the lower band). Supervisor decision
    T07: an event, not the level condition ``close > upper``."""

    name = "tf_bb_upper_cross"
    trigger = "event"
    edge_type = "TF"
    group = "channel_breakout"
    params = (
        _length("length", 20, (10, 20, 30, 40), 5, 100),
        _threshold("mult", 2.0, (1.5, 2.0, 2.5, 3.0), 0.5, 4.0, 0.1),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        bb = ind.bollinger(bars.close, _int(params, "length"), _float(params, "mult"))
        return crossover(bars.close, bb.upper)


@register
class TfSupertrendFlip(_Probe):
    """Supertrend(10, 3) turns to up-trend: direction goes from +1 to -1 (TradingView
    convention, -1 = up-trend). Short: the flip on the mirrored series."""

    name = "tf_supertrend_flip"
    trigger = "event"
    edge_type = "TF"
    group = "volatility_trailing"
    params = (
        _length("atr_period", 10, (7, 10, 14, 20), 2, 50),
        _threshold("factor", 3.0, (2.0, 2.5, 3.0, 3.5), 1.0, 5.0, 0.1),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        st = ind.supertrend(
            bars.high, bars.low, bars.close, _float(params, "factor"), _int(params, "atr_period")
        )
        return (st.direction == -1.0) & (_prev(st.direction) == 1.0)


@register
class TfIchimokuCloud(_Probe):
    """Ichimoku (9, 26, 52): close above the cloud and tenkan > kijun (short: below the cloud
    and tenkan < kijun).

    The cloud at bar ``i`` is the spans computed ``base - 1`` bars earlier — TradingView's
    built-in Ichimoku plots the spans with offset ``displacement - 1`` and displacement = 26 =
    ``base`` — so it uses only data up to bar ``i``.
    """

    name = "tf_ichimoku_cloud"
    trigger = "state"
    edge_type = "TF"
    group = "ichimoku"
    params = (
        _length("conversion", 9, (7, 9, 12, 15), 2, 20),
        _length("base", 26, (22, 26, 30, 40), 21, 60),
        _length("span_b", 52, (44, 52, 60, 80), 21, 120),
    )

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        base = _int(params, "base")
        ich = ind.ichimoku(
            bars.high, bars.low, _int(params, "conversion"), base, _int(params, "span_b")
        )
        shift = base - 1
        top = np.maximum(_prev(ich.span_a_raw, shift), _prev(ich.span_b_raw, shift))
        return (bars.close > top) & (ich.tenkan > ich.kijun)


@register
class TfRocCrossZero(_Probe):
    """ROC(20) crosses above 0 (short: crosses below 0).

    Implemented as momentum ``close - close[20]`` crossing 0, which has the same sign as ROC
    for positive prices and keeps the mirror rule exact (ROC is a ratio and is not
    translation-equivariant).
    """

    name = "tf_roc20_cross_zero"
    trigger = "event"
    edge_type = "TF"
    group = "momentum"
    params = (_length("length", 20, (10, 20, 40, 60), 2, 250),)

    @classmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        mom = ind.momentum(bars.close, _int(params, "length"))
        return (mom > 0.0) & (_prev(mom) <= 0.0)
