"""F-0.4.2: every fast indicator equals an independent naive implementation.

The naive versions below are plain Python loops over lists, written from the formulas (Pine
reference definitions and the conventions documented in the indicator docstrings). ``None``
plays the role of Pine's ``na``. Inputs are Hypothesis-generated valid OHLC series with
positive prices, including exact ties and zero-range bars (quarter-point prices).
"""

from __future__ import annotations

import math

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from strategy_factory.components import indicators as ind

EPS = 1e-10  # TradingView float-noise threshold (see indicators._core.TV_EPS)
# The first call of each kernel may include Numba JIT compilation (cold cache), which would
# trip Hypothesis' per-example deadline as a spurious "unreliable timing" failure.
NO_DEADLINE = settings(deadline=None)
Series = list[float | None]

# ----------------------------------------------------------------------------- inputs


@st.composite
def ohlc(draw: st.DrawFn, max_size: int = 70) -> tuple[list[float], ...]:
    n = draw(st.integers(1, max_size))
    price = st.one_of(
        st.floats(1.0, 1000.0, allow_nan=False, allow_infinity=False),
        st.integers(4, 10).map(lambda k: k / 4),  # coarse grid -> ties and flat windows
    )
    ext = st.one_of(st.just(0.0), st.floats(0.0, 0.05))
    rows = draw(st.lists(st.tuples(price, price, ext, ext), min_size=n, max_size=n))
    o = [r[0] for r in rows]
    c = [r[1] for r in rows]
    h = [max(r[0], r[1]) * (1.0 + r[2]) for r in rows]
    lo = [min(r[0], r[1]) * (1.0 - r[3]) for r in rows]
    return o, h, lo, c


lengths = st.integers(1, 12)


def arr(x: Series) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in x], dtype=np.float64)


def same(fast: np.ndarray, naive: Series) -> None:
    exp = arr(naive)
    assert fast.shape == exp.shape
    np.testing.assert_array_equal(np.isnan(fast), np.isnan(exp), err_msg="NaN positions")
    ok = ~np.isnan(exp)
    tol = 1e-9 * np.maximum(1.0, np.abs(exp[ok]))
    diff = np.abs(fast[ok] - exp[ok])
    assert np.all(diff <= tol), f"max diff {diff.max() if diff.size else 0}"


# ----------------------------------------------------------------------------- naive refs


def window(x: Series, i: int, n: int) -> list[float] | None:
    if i < n - 1:
        return None
    w = x[i - n + 1 : i + 1]
    return None if any(v is None for v in w) else [float(v) for v in w]  # type: ignore[arg-type]


def n_sma(x: Series, n: int) -> Series:
    out: Series = []
    for i in range(len(x)):
        w = window(x, i, n)
        out.append(None if w is None else sum(w) / n)
    return out


def n_smooth(x: Series, n: int, alpha: float) -> Series:
    out: Series = []
    prev: float | None = None
    for i in range(len(x)):
        if prev is None:
            w = window(x, i, n)
            val = None if w is None else sum(w) / n
        else:
            xi = x[i]
            val = None if xi is None else alpha * xi + (1.0 - alpha) * prev
        out.append(val)
        prev = val
    return out


def n_ema(x: Series, n: int) -> Series:
    return n_smooth(x, n, 2.0 / (n + 1))


def n_rma(x: Series, n: int) -> Series:
    return n_smooth(x, n, 1.0 / n)


def n_wma(x: Series, n: int) -> Series:
    out: Series = []
    for i in range(len(x)):
        w = window(x, i, n)
        if w is None:
            out.append(None)
            continue
        weights = list(range(1, n + 1))  # oldest 1 ... current n
        out.append(sum(a * b for a, b in zip(w, weights, strict=True)) / sum(weights))
    return out


def sub(a: Series, b: Series, k: float = 1.0) -> Series:
    return [None if u is None or v is None else k * u - v for u, v in zip(a, b, strict=True)]


def n_shift(x: Series, k: int) -> Series:
    return [x[i - k] if i >= k else None for i in range(len(x))]


def n_tr(h: Series, lo: Series, c: Series, handle_na: bool) -> Series:
    out: Series = []
    for i in range(len(h)):
        if i == 0:
            out.append(h[0] - lo[0] if handle_na else None)  # type: ignore[operator]
        else:
            pc = c[i - 1]
            out.append(max(h[i] - lo[i], abs(h[i] - pc), abs(lo[i] - pc)))  # type: ignore[operator]
    return out


def n_stdev(x: Series, n: int) -> Series:
    out: Series = []
    for i in range(len(x)):
        w = window(x, i, n)
        if w is None:
            out.append(None)
            continue
        m = sum(w) / n
        devs = [(v - m) if abs(v - m) > EPS else 0.0 for v in w]
        out.append(math.sqrt(sum(d * d for d in devs) / n))
    return out


def n_extreme(x: Series, n: int, use_max: bool) -> Series:
    out: Series = []
    for i in range(len(x)):
        w = window(x, i, n)
        out.append(None if w is None else (max(w) if use_max else min(w)))
    return out


def n_extreme_offset(x: Series, n: int, use_max: bool) -> Series:
    out: Series = []
    for i in range(len(x)):
        w = window(x, i, n)
        if w is None:
            out.append(None)
            continue
        target = max(w) if use_max else min(w)
        out.append(float(w.index(target) - (n - 1)))  # first occurrence = oldest bar
    return out


def n_rsi(x: Series, n: int) -> Series:
    gains: Series = [None]
    losses: Series = [None]
    for i in range(1, len(x)):
        a, b = x[i], x[i - 1]
        if a is None or b is None:
            gains.append(None)
            losses.append(None)
        else:
            gains.append(max(a - b, 0.0))
            losses.append(max(b - a, 0.0))
    up, dn = n_rma(gains, n), n_rma(losses, n)
    out: Series = []
    for u, d in zip(up, dn, strict=True):
        if u is None or d is None:
            out.append(None)
        elif d == 0.0:
            out.append(100.0)
        elif u == 0.0:
            out.append(0.0)
        else:
            out.append(100.0 - 100.0 / (1.0 + u / d))
    return out


def n_range_pos(h: Series, lo: Series, c: Series, n: int, ref_high: bool) -> Series:
    hh, ll = n_extreme(h, n, True), n_extreme(lo, n, False)
    out: Series = []
    for i in range(len(c)):
        a, b = hh[i], ll[i]
        if a is None or b is None or a == b:
            out.append(None)
        else:
            out.append(100.0 * (c[i] - (a if ref_high else b)) / (a - b))  # type: ignore[operator]
    return out


def n_percent_rank(x: Series, n: int) -> Series:
    out: Series = []
    for i in range(len(x)):
        cur = x[i]
        if i < n or cur is None:
            out.append(None)
            continue
        cnt = sum(1 for v in x[i - n : i] if v is not None and v <= cur)
        out.append(100.0 * cnt / n)
    return out


def n_streak(x: Series) -> Series:
    out: Series = []
    prev = 0.0  # nz(ud[1])
    for i in range(len(x)):
        if i > 0 and x[i] == x[i - 1]:
            ud = 0.0
        elif i > 0 and x[i] > x[i - 1]:  # type: ignore[operator]
            ud = 1.0 if prev <= 0 else prev + 1.0
        else:
            ud = -1.0 if prev >= 0 else prev - 1.0
        out.append(ud)
        prev = ud
    return out


def n_roc(x: Series, n: int) -> Series:
    p = n_shift(x, n)
    return [
        None if a is None or b is None else 100.0 * (a - b) / b for a, b in zip(x, p, strict=True)
    ]


def mean3(a: Series, b: Series, c: Series) -> Series:
    return [
        None if u is None or v is None or w is None else (u + v + w) / 3.0
        for u, v, w in zip(a, b, c, strict=True)
    ]


def n_fixnan(x: Series) -> Series:
    out: Series = []
    last: float | None = None
    for v in x:
        if v is not None:
            last = v
        out.append(last)
    return out


def n_dmi(h: Series, lo: Series, c: Series, n: int, m: int) -> tuple[Series, Series, Series]:
    pdm: Series = [None]
    mdm: Series = [None]
    for i in range(1, len(h)):
        up = h[i] - h[i - 1]  # type: ignore[operator]
        dn = lo[i - 1] - lo[i]  # type: ignore[operator]
        pdm.append(up if up - dn > EPS and up > 0 else 0.0)
        mdm.append(dn if dn - up > EPS and dn > 0 else 0.0)
    trur = n_rma(n_tr(h, lo, c, False), n)
    rp, rm = n_rma(pdm, n), n_rma(mdm, n)

    def di(r: Series) -> Series:
        return n_fixnan(
            [
                None if a is None or t is None or t == 0 else 100.0 * a / t
                for a, t in zip(r, trur, strict=True)
            ]
        )

    plus, minus = di(rp), di(rm)
    dx: Series = []
    for p, q in zip(plus, minus, strict=True):
        if p is None or q is None:
            dx.append(None)
        else:
            s = p + q
            dx.append(abs(p - q) / (1.0 if s == 0 else s))
    adx = [None if v is None else 100.0 * v for v in n_rma(dx, m)]
    return plus, minus, adx


def n_supertrend(h: Series, lo: Series, c: Series, f: float, n: int) -> tuple[Series, Series]:
    atr = n_rma(n_tr(h, lo, c, True), n)
    values: Series = []
    dirs: Series = []
    prev_up: float | None = None
    prev_lo: float | None = None
    prev_st: float | None = None
    for i in range(len(h)):
        hl2 = (h[i] + lo[i]) / 2.0  # type: ignore[operator]
        a = atr[i]
        up = None if a is None else hl2 + f * a
        dn = None if a is None else hl2 - f * a
        pu = prev_up if prev_up is not None else 0.0
        pl = prev_lo if prev_lo is not None else 0.0
        c1 = c[i - 1] if i > 0 else None
        keep_dn = (dn is not None and dn > pl) or (c1 is not None and c1 < pl)
        keep_up = (up is not None and up < pu) or (c1 is not None and c1 > pu)
        dn = dn if keep_dn else pl
        up = up if keep_up else pu
        if i == 0 or atr[i - 1] is None:
            d = 1.0
        elif prev_st is not None and prev_st == pu:
            d = -1.0 if (up is not None and c[i] > up) else 1.0  # type: ignore[operator]
        else:
            d = 1.0 if (dn is not None and c[i] < dn) else -1.0  # type: ignore[operator]
        st_ = dn if d == -1.0 else up
        values.append(st_)
        dirs.append(d)
        prev_up, prev_lo, prev_st = up, dn, st_
    return values, dirs


def n_psar(h: list[float], lo: list[float], c: list[float], s: float, inc: float, mx: float):
    out: Series = [None] * len(h)
    sar = ep = acc = 0.0
    long_ = False
    for i in range(1, len(h)):
        new_trend = i == 1
        if i == 1:
            long_ = c[1] > c[0]
            ep = h[1] if long_ else lo[1]
            sar = lo[0] if long_ else h[0]
            acc = s
        sar = sar + acc * (ep - sar)
        if long_ and sar > lo[i]:
            new_trend, long_, sar, ep, acc = True, False, max(h[i], ep), lo[i], s
        elif not long_ and sar < h[i]:
            new_trend, long_, sar, ep, acc = True, True, min(lo[i], ep), h[i], s
        if not new_trend:
            if long_ and h[i] > ep:
                ep, acc = h[i], min(acc + inc, mx)
            elif not long_ and lo[i] < ep:
                ep, acc = lo[i], min(acc + inc, mx)
        prior = [lo[i - 1]] + ([lo[i - 2]] if i > 1 else [])
        prior_h = [h[i - 1]] + ([h[i - 2]] if i > 1 else [])
        sar = min([sar, *prior]) if long_ else max([sar, *prior_h])
        out[i] = sar
    return out


# ----------------------------------------------------------------------------- tests


@NO_DEADLINE
@given(ohlc(), lengths)
def test_F_0_4_2_naive_moving_averages(bars, n: int) -> None:
    _, _, _, c = bars
    x = np.array(c)
    same(ind.sma(x, n), n_sma(c, n))
    same(ind.ema(x, n), n_ema(c, n))
    same(ind.rma(x, n), n_rma(c, n))
    same(ind.wma(x, n), n_wma(c, n))
    same(ind.sma_slope(x, n), sub(n_sma(c, n), n_shift(n_sma(c, n), 1)))


@NO_DEADLINE
@given(ohlc(), st.integers(2, 16))
def test_F_0_4_2_naive_hma(bars, n: int) -> None:
    c = bars[3]
    raw = sub(n_wma(c, n // 2), n_wma(c, n), 2.0)
    same(ind.hma(np.array(c), n), n_wma(raw, math.isqrt(n)))


@NO_DEADLINE
@given(ohlc(), st.integers(1, 12), st.integers(1, 5), st.integers(6, 40))
def test_F_0_4_2_naive_kama(bars, n: int, fast: int, slow: int) -> None:
    c = bars[3]
    fsc, ssc = 2.0 / (fast + 1), 2.0 / (slow + 1)
    exp: Series = []
    for i in range(len(c)):
        if i < n:
            exp.append(c[i])
            continue
        change = abs(c[i] - c[i - n])
        vol = sum(abs(c[k] - c[k - 1]) for k in range(i - n + 1, i + 1))
        er = change / vol if vol != 0 else 0.0
        sc = (er * (fsc - ssc) + ssc) ** 2
        prev = exp[-1]
        exp.append(prev + sc * (c[i] - prev))  # type: ignore[operator]
    same(ind.kama(np.array(c), n, fast, slow), exp)


@NO_DEADLINE
@given(ohlc(), lengths, st.floats(0.5, 3.0))
def test_F_0_4_2_naive_volatility(bars, n: int, mult: float) -> None:
    _, h, lo, c = bars
    H, L, C = np.array(h), np.array(lo), np.array(c)
    same(ind.true_range(H, L, C, True), n_tr(h, lo, c, True))
    same(ind.true_range(H, L, C, False), n_tr(h, lo, c, False))
    same(ind.atr(H, L, C, n), n_rma(n_tr(h, lo, c, True), n))
    sd = n_stdev(c, n)
    same(ind.stdev(C, n), sd)
    bb = ind.bollinger(C, n, mult)
    mid = n_sma(c, n)
    same(bb.mid, mid)
    same(bb.upper, [None if m is None else m + mult * s for m, s in zip(mid, sd, strict=True)])  # type: ignore[operator]
    same(bb.lower, [None if m is None else m - mult * s for m, s in zip(mid, sd, strict=True)])  # type: ignore[operator]
    for use_tr in (True, False):
        kc = ind.keltner(H, L, C, n, mult, use_tr)
        rng: Series = (
            n_tr(h, lo, c, False) if use_tr else [a - b for a, b in zip(h, lo, strict=True)]
        )
        width = n_ema(rng, n)
        kmid = n_ema(c, n)
        same(kc.mid, kmid)
        same(
            kc.upper,
            [
                None if m is None or w is None else m + mult * w
                for m, w in zip(kmid, width, strict=True)
            ],
        )
        same(
            kc.lower,
            [
                None if m is None or w is None else m - mult * w
                for m, w in zip(kmid, width, strict=True)
            ],
        )


@NO_DEADLINE
@given(ohlc(), lengths)
def test_F_0_4_2_naive_channels(bars, n: int) -> None:
    _, h, lo, _ = bars
    H, L = np.array(h), np.array(lo)
    same(ind.highest(H, n), n_extreme(h, n, True))
    same(ind.lowest(L, n), n_extreme(lo, n, False))
    same(ind.highest_bars(H, n), n_extreme_offset(h, n, True))
    same(ind.lowest_bars(L, n), n_extreme_offset(lo, n, False))
    dc = ind.donchian(H, L, n)
    same(dc.upper, n_extreme(h, n, True))
    same(dc.lower, n_extreme(lo, n, False))
    up = ind.aroon(H, L, n)
    same(
        up.up,
        [None if v is None else 100.0 * (v + n) / n for v in n_extreme_offset(h, n + 1, True)],
    )
    same(
        up.down,
        [None if v is None else 100.0 * (v + n) / n for v in n_extreme_offset(lo, n + 1, False)],
    )


@NO_DEADLINE
@given(ohlc(), st.integers(1, 6), st.integers(7, 12), st.integers(13, 20))
def test_F_0_4_2_naive_ichimoku(bars, a: int, b: int, s: int) -> None:
    _, h, lo, _ = bars

    def mid(n: int) -> Series:
        return [
            None if x is None or y is None else (y + x) / 2.0
            for x, y in zip(n_extreme(h, n, True), n_extreme(lo, n, False), strict=True)
        ]

    ich = ind.ichimoku(np.array(h), np.array(lo), a, b, s)
    same(ich.tenkan, mid(a))
    same(ich.kijun, mid(b))
    same(
        ich.span_a_raw,
        [
            None if x is None or y is None else (x + y) / 2.0
            for x, y in zip(mid(a), mid(b), strict=True)
        ],
    )
    same(ich.span_b_raw, mid(s))


@NO_DEADLINE
@given(ohlc(), lengths)
def test_F_0_4_2_naive_oscillators(bars, n: int) -> None:
    _, h, lo, c = bars
    H, L, C = np.array(h), np.array(lo), np.array(c)
    same(ind.rsi(C, n), n_rsi(c, n))
    same(
        ind.ibs(H, L, C),
        [None if a == b else (x - b) / (a - b) for a, b, x in zip(h, lo, c, strict=True)],
    )
    m, sd = n_sma(c, n), n_stdev(c, n)
    same(
        ind.zscore(C, n),
        [None if s is None or s == 0 else (x - mm) / s for x, mm, s in zip(c, m, sd, strict=True)],  # type: ignore[operator]
    )
    same(ind.roc(C, n), n_roc(c, n))
    same(ind.momentum(C, n), sub(c, n_shift(c, n)))
    same(ind.williams_r(H, L, C, n), n_range_pos(h, lo, c, n, True))
    raw = n_range_pos(h, lo, c, n, False)
    k = n_sma(raw, 3)
    stoch = ind.stochastic(H, L, C, n, 3, 2)
    same(stoch.k, k)
    same(stoch.d, n_sma(k, 2))
    same(ind.percent_rank(C, n), n_percent_rank(c, n))
    same(ind.updown_streak(C), n_streak(c))


@NO_DEADLINE
@given(ohlc(), st.integers(1, 6), st.integers(7, 12), st.integers(1, 5))
def test_F_0_4_2_naive_macd(bars, fast: int, slow: int, sig: int) -> None:
    c = bars[3]
    line = sub(n_ema(c, fast), n_ema(c, slow))
    signal = n_ema(line, sig)
    m = ind.macd(np.array(c), fast, slow, sig)
    same(m.line, line)
    same(m.signal, signal)
    same(m.hist, sub(line, signal))


@NO_DEADLINE
@given(ohlc(), st.integers(1, 4), st.integers(1, 3), st.integers(1, 10))
def test_F_0_4_2_naive_connors_rsi(bars, a: int, b: int, r: int) -> None:
    c = bars[3]
    exp = mean3(n_rsi(c, a), n_rsi(n_streak(c), b), n_percent_rank(n_roc(c, 1), r))
    same(ind.connors_rsi(np.array(c), a, b, r), exp)


@NO_DEADLINE
@given(ohlc(), lengths, lengths)
def test_F_0_4_2_naive_dmi(bars, n: int, m: int) -> None:
    _, h, lo, c = bars
    d = ind.dmi(np.array(h), np.array(lo), np.array(c), n, m)
    plus, minus, adx = n_dmi(h, lo, c, n, m)
    same(d.plus, plus)
    same(d.minus, minus)
    same(d.adx, adx)


@NO_DEADLINE
@given(ohlc(), lengths, st.floats(0.5, 4.0))
def test_F_0_4_2_naive_supertrend(bars, n: int, f: float) -> None:
    _, h, lo, c = bars
    st_ = ind.supertrend(np.array(h), np.array(lo), np.array(c), f, n)
    values, dirs = n_supertrend(h, lo, c, f, n)
    same(st_.value, values)
    same(st_.direction, dirs)


@NO_DEADLINE
@given(ohlc(), st.floats(0.01, 0.05), st.floats(0.01, 0.05), st.floats(0.1, 0.3))
def test_F_0_4_2_naive_psar(bars, s: float, inc: float, mx: float) -> None:
    _, h, lo, c = bars
    same(ind.psar(np.array(h), np.array(lo), np.array(c), s, inc, mx), n_psar(h, lo, c, s, inc, mx))
