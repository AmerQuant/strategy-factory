"""F-2.1 / F-2.2: the stage-2 method library (T13 §4, §9; D-622, D-626 ... D-635).

* every method declares 2-4 values per parameter, <= 3 parameters, <= 64 cells (D-630);
* no method ever signals before its declared warm-up (the baseline's allowed range, D-615);
* the ratio rules are mirror-exact in the ``|ref|`` form (D-632);
* each of the user's rules equals a **naive line-by-line port** of
  ``tools/tradingview/user_mr_suite.pine`` at the script's parameters (T13 §9), on random data;
* D-627: no two methods produce identical signal vectors on the parity charts at their default
  cells, and the guard catches a registered duplicate (mutation check).
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from typing import Any, ClassVar

import numpy as np
import pytest

from strategy_factory.components import indicators as ind
from strategy_factory.components.base import Bars, BoolArray, ParamValue, coarse_cells
from strategy_factory.components.entries.methods_mr import MrRsi
from strategy_factory.components.registry import default_registry
from strategy_factory.selftest.parity_refs import (
    fixture,
    fixture_dir,
    load_chart_data,
    load_manifest,
)
from strategy_factory.stages.screen import method_cells
from strategy_factory.stages.screen_config import load_s02_config

METHODS = sorted(
    (c for c in default_registry().entries() if getattr(c, "screen", False)), key=lambda c: c.name
)
BY_NAME = {c.name: c for c in METHODS}


def random_walk(seed: int, n: int = 400, vol: float = 0.02) -> Bars:
    rng = np.random.default_rng(seed)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0.0, vol, n)))
    o = np.concatenate(([100.0], c[:-1]))
    w = np.abs(rng.normal(0.0, vol / 2, (2, n)))
    return Bars(o, np.maximum(o, c) * (1 + w[0]), np.minimum(o, c) * (1 - w[1]), c)


def prev(x: np.ndarray, k: int = 1) -> np.ndarray:
    out = np.full(x.shape[0], np.nan)
    out[k:] = x[:-k]
    return out


# ------------------------------------------------------------------ the library and the grid
def test_F_2_1_the_library_is_complete_and_listed() -> None:
    """20 MR + 15 TF methods (D-627, D-630 split, D-635 no dual momentum), every one in the
    stage config, which loads (its registry check passes)."""
    cfg = load_s02_config()
    mr = {c.name for c in METHODS if c.edge_type == "MR"}
    tf = {c.name for c in METHODS if c.edge_type == "TF"}
    assert len(mr) == 20 and len(tf) == 15
    assert set(cfg.methods["MR"]) == mr and set(cfg.methods["TF"]) == tf
    assert "mr_ma_distance_pct" in mr and "mr_ma_distance_atr" in mr  # D-630
    assert not any("dual" in n for n in tf)  # D-635


@pytest.mark.parametrize("comp", METHODS, ids=lambda c: c.name)
def test_F_2_1_every_method_respects_the_coarse_grid(comp: Any) -> None:
    assert 1 <= len(comp.params) <= 3  # T13 §4: at most 3 free parameters
    assert all(2 <= len(p.coarse_values) <= 4 for p in comp.params)  # D-630
    assert coarse_cells(comp.params) <= 64  # D-110
    assert len(method_cells(comp.name)) == coarse_cells(comp.params)


def test_F_2_1_d633_williams_has_both_readings() -> None:
    confirm = {p.name: p for p in BY_NAME["mr_williams_confirm"].params}["confirm"]
    assert set(confirm.coarse_values) >= {"same_bar", "latched"}


def test_F_2_1_d634_n_day_low_source_is_a_choice() -> None:
    source = {p.name: p for p in BY_NAME["mr_n_day_low"].params}["source"]
    assert source.coarse_values == ("low", "close") and source.default == "low"


# ------------------------------------------------------------------ warm-up
SERIES = [random_walk(s) for s in range(12)]


@pytest.mark.parametrize("comp", METHODS, ids=lambda c: c.name)
def test_F_2_1_no_method_signals_before_its_warmup(comp: Any) -> None:
    for params in method_cells(comp.name):
        w = comp.warmup(params)
        assert w >= 0
        for b in SERIES:
            lo, sh = comp.signals(b, params)
            assert not (lo[:w].any() or sh[:w].any()), (comp.name, params, w)


def test_F_2_1_the_warmup_check_catches_a_late_warmup() -> None:
    """Mutation: RSI(2) declared to warm up at 1 instead of 2 -- its signal at bar 2 would sit
    at the declared warm-up; declaring 3 is caught by the signal at bar 2."""

    class TooLate(MrRsi):
        @classmethod
        def warmup(cls, params: Mapping[str, ParamValue]) -> int:
            return 3

    hits = [
        np.flatnonzero(
            TooLate.signals(b, {"n": 2, "t": 35.0})[0] | TooLate.signals(b, {"n": 2, "t": 35.0})[1]
        )
        for b in SERIES
    ]
    earliest = min(int(h[0]) for h in hits if h.size)
    assert earliest < TooLate.warmup({"n": 2, "t": 35.0})


# ------------------------------------------------------------------ mirror (D-632)
@pytest.mark.parametrize("seed", range(5))
def test_F_2_1_d632_ratio_rules_mirror_exactly(seed: int) -> None:
    """The short of a ratio rule is the literal ``x > ref * (1 + f)`` for positive prices."""
    b = random_walk(seed, n=600)
    c = b.close
    _, short = BY_NAME["mr_daily_drop"].signals(b, {"d": 1.0, "atr_expanding": "off"})
    assert np.array_equal(short, np.nan_to_num(c > prev(c) * 1.01, nan=0).astype(bool))
    ema = ind.ema(c, 10)
    _, short = BY_NAME["mr_ma_distance_pct"].signals(b, {"n": 10, "p": 2.0})
    with np.errstate(invalid="ignore"):
        assert np.array_equal(short, c > ema * 1.02)
    ema5 = ind.ema(c, 5)
    _, short = BY_NAME["mr_ema_slope_drop"].signals(b, {"n": 5, "p": 0.5})
    with np.errstate(invalid="ignore"):
        assert np.array_equal(short, ema5 > prev(ema5) * 1.005)


#: rules on price ratios (D-632): mirror-exact under negation in the |ref| form, but no
#: reflection p -> K - p is exact for a ratio (it is scale-, not translation-invariant)
RATIO_METHODS = {"mr_daily_drop", "mr_ma_distance_pct", "mr_ema_slope_drop", "mr_connors_rsi"}


@pytest.mark.parametrize("comp", METHODS, ids=lambda c: c.name)
def test_F_2_1_d626_the_short_is_the_long_on_negated_prices(comp: Any) -> None:
    """The mirror rule by construction (``Bars.mirrored``), and both sides fire."""
    b = random_walk(3, n=800)
    for params in method_cells(comp.name)[:: max(1, len(method_cells(comp.name)) // 6)]:
        lo, sh = comp.signals(b, params)
        m_long, m_short = comp.signals(b.mirrored(), params)
        assert np.array_equal(sh, m_long) and np.array_equal(lo, m_short), (comp.name, params)
    lo, sh = comp.signals(b, default_cell(comp))
    assert lo.any() and sh.any(), comp.name


@pytest.mark.parametrize(
    "comp", [c for c in METHODS if c.name not in RATIO_METHODS], ids=lambda c: c.name
)
def test_F_2_1_d626_translation_invariant_methods_mirror_on_a_positive_scale(comp: Any) -> None:
    """As T07's probe test: the short equals the long on ``K - p`` (high and low swap)."""
    b = random_walk(5, n=600)
    k = 4.0 * float(b.high.max())
    reflected = Bars(k - b.open, k - b.low, k - b.high, k - b.close)
    for params in method_cells(comp.name)[:: max(1, len(method_cells(comp.name)) // 6)]:
        _, sh = comp.signals(b, params)
        m_long, _ = comp.signals(reflected, params)
        assert np.array_equal(sh, m_long), (comp.name, params)


@pytest.mark.parametrize("seed", range(3))
def test_F_2_1_d632_connors_is_the_golden_indicator_for_positive_prices(seed: int) -> None:
    """The |ref| ROC changes nothing for positive prices: the T07 golden-tested indicator."""
    from strategy_factory.components.entries.methods_mr import connors_rsi_mirrorable

    c = random_walk(seed, n=500).close
    for rl in (2, 3, 5):
        np.testing.assert_allclose(
            connors_rsi_mirrorable(c, rl, 2, 100), ind.connors_rsi(c, rl, 2, 100), equal_nan=True
        )


def test_F_2_1_d632_the_literal_ratio_form_would_break_the_mirror() -> None:
    """Why the |ref| form: the literal ``c < c[1] * 0.99`` mirrored fires on most bars."""
    b = random_walk(1, n=600)
    m = b.mirrored()
    with np.errstate(invalid="ignore"):
        naive = m.close < prev(m.close) * 0.99
    _, short = BY_NAME["mr_daily_drop"].signals(b, {"d": 1.0, "atr_expanding": "off"})
    assert naive.mean() > 0.5 > short.mean()


# ------------------------------------------------------------------ naive ports of the script
def pine_ibs(b: Bars) -> np.ndarray:
    return np.array(
        [
            (c - lo) / (h - lo) * 100 if h != lo else np.nan
            for h, lo, c in zip(b.high, b.low, b.close, strict=True)
        ]
    )


def pine_candle_total(b: Bars) -> np.ndarray:
    """Lines 329-331, bar by bar (bar 0 NaN: no previous bar, see ``candle_total``)."""
    out = np.full(len(b), np.nan)
    for i in range(1, len(b)):
        c, h, lo, h1, l1 = b.close[i], b.high[i], b.low[i], b.high[i - 1], b.low[i - 1]
        if 5 * c > 4 * h + lo:
            s = 2
        elif 5 * c > 3 * h + 2 * lo:
            s = 1
        elif 5 * c > 2 * h + 3 * lo:
            s = 0
        elif 5 * c > h + 4 * lo:
            s = -1
        else:
            s = -2
        if c > h1:
            co = 3
        elif 3 * c > 2 * h1 + l1:
            co = 2
        elif 3 * c > h1 + 2 * l1:
            co = 0
        elif c > l1:
            co = -2
        else:
            co = -3
        out[i] = s + co
    return out


def pine_base_candle(b: Bars) -> np.ndarray:
    """Lines 387-413 with the script's own thirds; returns ``direction``."""
    base_high, base_low, long_dir = b.high[0], b.low[0], True
    out = np.zeros(len(b))
    for i in range(len(b)):
        o, h, lo, c = b.open[i], b.high[i], b.low[i], b.close[i]
        if (long_dir and 3 * c > 2 * h + lo and c > o and h > base_high) or (
            (not long_dir) and 3 * c < h + 2 * lo and c < o and lo < base_low
        ):
            base_high, base_low = h, lo
        elif long_dir and 3 * c < h + 2 * lo and c < o and c < base_low:
            base_high, base_low, long_dir = h, lo, False
        elif (not long_dir) and 3 * c > 2 * h + lo and c > o and c > base_high:
            base_high, base_low, long_dir = h, lo, True
        out[i] = 1 if long_dir else -1
    return out


def pine_williams(b: Bars, n: int) -> np.ndarray:
    out = np.full(len(b), np.nan)
    for i in range(n - 1, len(b)):
        hh, ll = b.high[i - n + 1 : i + 1].max(), b.low[i - n + 1 : i + 1].min()
        out[i] = 100 * (b.close[i] - ll) / (hh - ll)
    return out


def ports(b: Bars) -> list[tuple[str, dict[str, Any], np.ndarray]]:
    """(method, the script's parameters, the naive long signal) for every user rule."""
    c, h, lo = b.close, b.high, b.low
    ibs = pine_ibs(b)
    rsi2, rsi5 = ind.rsi(c, 2), ind.rsi(c, 5)
    atr5, atr10 = ind.atr(h, lo, c, 5), ind.atr(h, lo, c, 10)
    ema5 = ind.ema(c, 5)
    hist = ind.macd(c, 12, 26, 9).hist
    tot = pine_candle_total(b)
    tm = tot + prev(tot) + prev(tot, 2)
    w5 = pine_williams(b, 5)
    d = pine_base_candle(b)
    low5 = np.array([lo[max(0, i - 5) : i].min() if i >= 5 else np.nan for i in range(len(b))])
    high10 = np.array([h[i - 10 : i].max() if i >= 10 else np.nan for i in range(len(b))])
    band = ind.lowest(lo, 10) + 2.5 * ind.atr(h, lo, c, 25)
    c1 = prev(c)
    with np.errstate(invalid="ignore"):
        rows = [
            ("mr_ibs", {"t": 30.0, "k": 1}, ibs < 30),  # #0 (ibs_NumConn 1)
            ("mr_ibs", {"t": 30.0, "k": 2}, (ibs < 30) & (prev(ibs) < 30)),
            ("mr_rsi", {"n": 2, "t": 20.0}, rsi2 <= 20),  # #1
            ("mr_rsi", {"n": 5, "t": 35.0}, rsi5 <= 35),  # #19
            ("mr_rsi_sum", {"n": 2, "m": 2, "level": 10.0}, rsi2 + prev(rsi2) < 20),  # #2
            (
                "mr_lower_lows",
                {"k": 3},
                (lo < prev(lo)) & (prev(lo) < prev(lo, 2)) & (prev(lo, 2) < prev(lo, 3)),
            ),  # 3
            ("mr_down_closes", {"k": 2}, (c < c1) & (c1 < prev(c, 2))),  # #4
            ("mr_n_day_low", {"n": 5, "source": "low"}, c < low5),  # #5
            ("mr_daily_drop", {"d": 1.0, "atr_expanding": "off"}, c < c1 * 0.99),  # #7
            (
                "mr_daily_drop",
                {"d": 1.0, "atr_expanding": "on"},
                (c < c1 * 0.99) & (atr5 > atr10),
            ),  # 6 (|ref| form)
            ("mr_ma_distance_atr", {"n": 5, "a": 0.5}, c + atr5 * 0.5 < ema5),  # #8
            ("mr_ma_distance_pct", {"n": 5, "p": 1.0}, c < ema5 * 0.99),  # #9 (|ref| form)
            (
                "mr_ema_slope_drop",
                {"n": 5, "p": 0.5},
                ema5 < prev(ema5) * 0.995,
            ),  # #10 (|ref| form)
            ("mr_ibs_after_new_high", {"n": 10, "t": 15.0}, (h > high10) & (ibs < 15)),  # #14
            (
                "mr_macd_hist_falling",
                {"k": 4},
                (hist < prev(hist))
                & (prev(hist) < prev(hist, 2))
                & (prev(hist, 2) < prev(hist, 3))
                & (prev(hist, 3) < prev(hist, 4))
                & (hist < 0)
                & (c < c1),
            ),  # 17
            ("mr_candle_score", {"n": 3, "level": -7 / 3, "mode": "level"}, tm <= -7),  # #18
            (
                "mr_candle_score",
                {"n": 3, "level": -7 / 3, "mode": "rising"},
                (tm > prev(tm)) & (tm <= -7),
            ),  # 18 rising
            (
                "mr_macd_hist_turn",
                {"k": 2},
                (hist > prev(hist)) & (prev(hist) > prev(hist, 2)) & (hist < 0),
            ),  # 20
            (
                "mr_williams_confirm",
                {"n": 5, "t": 20.0, "confirm": "same_bar"},
                (w5 < 20) & (h > prev(h)),
            ),  # 22 as run
            ("tf_atr_band", {"n": 10, "k": 2.5, "m": 25}, c > band),  # #11
            ("tf_base_candle", {"frac": 1 / 3}, (d == 1) & (prev(d) == -1)),  # #23
        ]
    return rows


@pytest.mark.parametrize("seed", range(4))
def test_F_2_1_the_user_rules_equal_a_naive_port_of_the_script(seed: int) -> None:
    b = random_walk(seed, n=700)
    for name, params, naive in ports(b):
        got, _ = BY_NAME[name].signals(b, params)
        np.testing.assert_array_equal(got, np.asarray(naive, bool), err_msg=f"{name} {params}")


def test_F_2_1_d633_latched_is_the_intended_trigger() -> None:
    """``latched``: armed by %R < t, fired by the first bar with a higher high; hand case."""
    close = np.array([10.0, 9.0, 8.0, 7.5, 7.6, 7.7, 9.5])
    high = np.array([10.5, 9.5, 8.5, 8.0, 7.9, 7.95, 9.8])  # higher highs only at bars 5 and 6
    low = close - 0.5
    b = Bars(close, high, low, close)
    same, _ = BY_NAME["mr_williams_confirm"].signals(b, {"n": 3, "t": 20.0, "confirm": "same_bar"})
    latched, _ = BY_NAME["mr_williams_confirm"].signals(
        b, {"n": 3, "t": 20.0, "confirm": "latched"}
    )
    w = pine_williams(b, 3)
    armed = np.flatnonzero(w < 20)
    assert armed.size and armed[0] < 5
    assert latched[5] and not same[5]  # the latch fires on the first higher high after arming


# ------------------------------------------------------------------ D-627 equivalence guard
def duplicates(signals: dict[str, tuple[np.ndarray, np.ndarray]]) -> list[tuple[str, str]]:
    seen: dict[bytes, str] = {}
    out = []
    for name, (lo, sh) in sorted(signals.items()):
        key = lo.tobytes() + sh.tobytes()
        if key in seen:
            out.append((seen[key], name))
        else:
            seen[key] = name
    return out


def chart_bars(name: str) -> Bars:
    ch = load_chart_data(fixture(name), load_manifest(fixture_dir()))
    return Bars(ch.open, ch.high, ch.low, ch.close)


def default_cell(comp: Any) -> dict[str, Any]:
    return {p.name: p.default for p in comp.params}


@pytest.mark.parametrize("chart", ["BATS_SPY, 1D.csv", "OANDA_XAUUSD, 60.csv"])
def test_F_2_1_d627_no_two_methods_produce_the_same_signals(chart: str) -> None:
    b = chart_bars(chart)
    sig = {c.name: c.signals(b, default_cell(c)) for c in METHODS}
    assert all(lo.any() or sh.any() for lo, sh in sig.values())
    assert duplicates(sig) == []


def test_F_2_1_d627_the_guard_catches_a_registered_duplicate() -> None:
    """Mutation check: a second method with the RSI rule under another name is caught."""

    class Copy(MrRsi):
        name: ClassVar[str] = "mr_rsi_copy"

        @classmethod
        def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
            return MrRsi.long_signals(bars, params)

    b = chart_bars("BATS_SPY, 1D.csv")
    sig = {c.name: c.signals(b, default_cell(c)) for c in METHODS}
    sig["mr_rsi_copy"] = Copy.signals(b, default_cell(MrRsi))
    assert ("mr_rsi", "mr_rsi_copy") in duplicates(sig)


def test_F_2_1_d627_distinct_rules_that_look_alike_stay_distinct() -> None:
    """The pairs the plan checked: the MACD rise vs trough, smoothed %K vs raw %R."""
    b = chart_bars("BATS_SPY, 1D.csv")
    for a, pa, c, pc in [
        ("mr_macd_hist_turn", {"k": 1}, "mr_macd_hist_trough", {"w": 3}),
        (
            "mr_stochastic_k",
            {"n": 5, "t": 20.0},
            "mr_williams_confirm",
            {"n": 5, "t": 20.0, "confirm": "off"},
        ),
    ]:
        assert not np.array_equal(BY_NAME[a].signals(b, pa)[0], BY_NAME[c].signals(b, pc)[0])


def test_F_2_1_cell_order_is_the_declaration_product() -> None:
    comp = BY_NAME["mr_rsi_sum"]
    cells = method_cells(comp.name)
    expected = list(itertools.product(*(p.coarse_values for p in comp.params)))
    assert [tuple(c.values()) for c in cells] == expected
