"""F-0.4.2: indicator values equal TradingView's golden exports.

Each golden file carries TradingView's own OHLC, so these tests feed that OHLC into our
functions and compare with the plot columns — independent of our data sources.

* NaN warm-up positions must match exactly;
* values must satisfy ``|ours - tv| <= 1e-6 * max(1, |tv|)`` over all bars where both are
  non-NaN, loosened by half a unit of the export's last decimal only if the export is rounded
  (detected per file from the printed decimals).
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
import pytest
from fixtures.tv_golden_io import (
    BASE_COLUMNS,
    GoldenFile,
    golden_files,
    load_golden,
    pine_plot_titles,
)

from strategy_factory.components import indicators as ind

pytestmark = pytest.mark.parity

REL_TOL = 1e-6

# Columns compared only on bars where the golden value is non-NaN (NaN warm-up not checked).
# CONNORS_RSI_3_2_100: the committed exports were made with the original Pine helper
# `updown`, which read `ud[1]` without `nz()`, so its streak (and Connors RSI) stayed na until
# the first unchanged close. Our streak follows TradingView's built-in Connors RSI (`nz`
# semantics, defined from bar 0); the Pine script now uses `nz(ud[1])`. From the first
# unchanged close onward both streaks are identical, but the golden `rsi(streak, 2)` was
# SMA-seeded there while ours carries RMA memory from bar 0; that difference halves every bar
# (alpha = 1/2). The column is therefore checked by `test_F_0_4_2_golden_connors_rsi` below.
# Remove this special case once the exports are redone with the fixed script.
GOLDEN_NON_NAN_ONLY = {"CONNORS_RSI_3_2_100"}
# RSI parts are in [0, 100] and enter the mean with weight 1/3, so the seed difference is at
# most 100/3 and falls below 1e-6 after ceil(log2(100/3 / 1e-6)) = 25 bars (alpha = 1/2).
CRSI_SEED_DECAY_BARS = math.ceil(math.log2((100 / 3) / REL_TOL))

Ohlc = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]


def _kc(o: np.ndarray, h: np.ndarray, lo: np.ndarray, c: np.ndarray) -> ind.Bands:
    return ind.keltner(h, lo, c, 20, 2.0)


COLUMNS: dict[str, Callable[[np.ndarray, np.ndarray, np.ndarray, np.ndarray], np.ndarray]] = {
    "SMA_20": lambda o, h, lo, c: ind.sma(c, 20),
    "SMA_50": lambda o, h, lo, c: ind.sma(c, 50),
    "SMA_100": lambda o, h, lo, c: ind.sma(c, 100),
    "SMA_200": lambda o, h, lo, c: ind.sma(c, 200),
    "EMA_20": lambda o, h, lo, c: ind.ema(c, 20),
    "EMA_50": lambda o, h, lo, c: ind.ema(c, 50),
    "EMA_100": lambda o, h, lo, c: ind.ema(c, 100),
    "SMA_50_SLOPE": lambda o, h, lo, c: ind.sma_slope(c, 50),
    "HMA_20": lambda o, h, lo, c: ind.hma(c, 20),
    "KAMA_10_2_30": lambda o, h, lo, c: ind.kama(c, 10, 2, 30),
    "ATR_14": lambda o, h, lo, c: ind.atr(h, lo, c, 14),
    "BB_20_2_MID": lambda o, h, lo, c: ind.bollinger(c, 20, 2.0).mid,
    "BB_20_2_UP": lambda o, h, lo, c: ind.bollinger(c, 20, 2.0).upper,
    "BB_20_2_LO": lambda o, h, lo, c: ind.bollinger(c, 20, 2.0).lower,
    "KC_20_2_MID": lambda o, h, lo, c: _kc(o, h, lo, c).mid,
    "KC_20_2_UP": lambda o, h, lo, c: _kc(o, h, lo, c).upper,
    "KC_20_2_LO": lambda o, h, lo, c: _kc(o, h, lo, c).lower,
    "DC_10_HI": lambda o, h, lo, c: ind.donchian(h, lo, 10).upper,
    "DC_10_LO": lambda o, h, lo, c: ind.donchian(h, lo, 10).lower,
    "DC_20_HI": lambda o, h, lo, c: ind.donchian(h, lo, 20).upper,
    "DC_20_LO": lambda o, h, lo, c: ind.donchian(h, lo, 20).lower,
    "DC_55_HI": lambda o, h, lo, c: ind.donchian(h, lo, 55).upper,
    "DC_55_LO": lambda o, h, lo, c: ind.donchian(h, lo, 55).lower,
    "LOWEST_CLOSE_7": lambda o, h, lo, c: ind.lowest(c, 7),
    "RSI_2": lambda o, h, lo, c: ind.rsi(c, 2),
    "RSI_5": lambda o, h, lo, c: ind.rsi(c, 5),
    "RSI_14": lambda o, h, lo, c: ind.rsi(c, 14),
    "IBS": lambda o, h, lo, c: ind.ibs(h, lo, c),
    "ZSCORE_20": lambda o, h, lo, c: ind.zscore(c, 20),
    "MACD_12_26_9_LINE": lambda o, h, lo, c: ind.macd(c, 12, 26, 9).line,
    "MACD_12_26_9_SIGNAL": lambda o, h, lo, c: ind.macd(c, 12, 26, 9).signal,
    "MACD_12_26_9_HIST": lambda o, h, lo, c: ind.macd(c, 12, 26, 9).hist,
    "ROC_20": lambda o, h, lo, c: ind.roc(c, 20),
    "WPR_14": lambda o, h, lo, c: ind.williams_r(h, lo, c, 14),
    "STOCH_14_3_K": lambda o, h, lo, c: ind.stochastic(h, lo, c, 14, 3, 3).k,
    "STOCH_14_3_3_D": lambda o, h, lo, c: ind.stochastic(h, lo, c, 14, 3, 3).d,
    "CONNORS_RSI_3_2_100": lambda o, h, lo, c: ind.connors_rsi(c, 3, 2, 100),
    "DI_PLUS_14": lambda o, h, lo, c: ind.dmi(h, lo, c, 14, 14).plus,
    "DI_MINUS_14": lambda o, h, lo, c: ind.dmi(h, lo, c, 14, 14).minus,
    "ADX_14": lambda o, h, lo, c: ind.dmi(h, lo, c, 14, 14).adx,
    "SUPERTREND_10_3": lambda o, h, lo, c: ind.supertrend(h, lo, c, 3.0, 10).value,
    "SUPERTREND_10_3_DIR": lambda o, h, lo, c: ind.supertrend(h, lo, c, 3.0, 10).direction,
    "PSAR_002_02": lambda o, h, lo, c: ind.psar(h, lo, c, 0.02, 0.02, 0.2),
    "AROON_25_UP": lambda o, h, lo, c: ind.aroon(h, lo, 25).up,
    "AROON_25_DOWN": lambda o, h, lo, c: ind.aroon(h, lo, 25).down,
    "ICHI_TENKAN_9": lambda o, h, lo, c: ind.ichimoku(h, lo, 9, 26, 52).tenkan,
    "ICHI_KIJUN_26": lambda o, h, lo, c: ind.ichimoku(h, lo, 9, 26, 52).kijun,
    "ICHI_SPAN_A_RAW": lambda o, h, lo, c: ind.ichimoku(h, lo, 9, 26, 52).span_a_raw,
    "ICHI_SPAN_B_52_RAW": lambda o, h, lo, c: ind.ichimoku(h, lo, 9, 26, 52).span_b_raw,
}

FILES = golden_files()
NO_FILES_REASON = (
    "no TradingView golden exports in tests/fixtures/tv_golden/ "
    "(export sf_golden_indicators.pine per T07 and add <EXCHANGE>_<SYMBOL>_<TF>.csv.gz)"
)


def tolerance(golden: GoldenFile, tv: np.ndarray) -> np.ndarray:
    """Per-value absolute tolerance for one column."""
    tol = REL_TOL * np.maximum(1.0, np.abs(tv))
    if golden.rounded:
        tol = np.maximum(tol, 0.5 * 10.0 ** (-golden.export_decimals))
    return tol


def compare(golden: GoldenFile, column: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(ours, tv, tolerance) for ``column`` of ``golden``."""
    g = golden.columns
    ours = COLUMNS[column](g["open"], g["high"], g["low"], g["close"])
    tv = g[column]
    return ours, tv, tolerance(golden, tv)


def test_F_0_4_2_every_pine_plot_is_mapped() -> None:
    titles = pine_plot_titles()
    assert len(titles) == len(set(titles)) == 49
    assert sorted(titles) == sorted(COLUMNS)


@pytest.mark.skipif(not FILES, reason=NO_FILES_REASON)
@pytest.mark.parametrize("path", FILES, ids=[p.name.removesuffix(".csv.gz") for p in FILES])
def test_F_0_4_2_golden_file_has_every_plot(path) -> None:
    golden = load_golden(path)
    missing = [t for t in pine_plot_titles() if t not in golden.columns]
    assert not missing, f"{golden.name}: plot columns missing from the export: {missing}"
    for base in BASE_COLUMNS:
        assert base in golden.columns


@pytest.mark.skipif(not FILES, reason=NO_FILES_REASON)
@pytest.mark.parametrize("column", sorted(set(COLUMNS) - GOLDEN_NON_NAN_ONLY))
@pytest.mark.parametrize("path", FILES, ids=[p.name.removesuffix(".csv.gz") for p in FILES])
def test_F_0_4_2_golden_values(path, column: str) -> None:
    golden = load_golden(path)
    ours, tv, tol = compare(golden, column)

    ours_nan, tv_nan = np.isnan(ours), np.isnan(tv)
    if column in GOLDEN_NON_NAN_ONLY:
        missing = np.flatnonzero(ours_nan & ~tv_nan)
        assert missing.size == 0, f"{golden.name}/{column}: NaN where TradingView has a value"
        assert (~tv_nan).any(), f"{golden.name}/{column}: no golden values to compare"
    else:
        mismatch = np.flatnonzero(ours_nan != tv_nan)
        assert mismatch.size == 0, (
            f"{golden.name}/{column}: NaN positions differ at {mismatch.size} bars, "
            f"first at bar {mismatch[0]} (ours={ours[mismatch[0]]}, tv={tv[mismatch[0]]})"
        )

    both = ~ours_nan & ~tv_nan
    err = np.abs(ours[both] - tv[both])
    bad = np.flatnonzero(err > tol[both])
    if bad.size:
        idx = np.flatnonzero(both)[bad[0]]
        pytest.fail(
            f"{golden.name}/{column}: {bad.size} bars outside tolerance, first at bar {idx}: "
            f"ours={ours[idx]!r} tv={tv[idx]!r} max_abs_err={err.max():.3e}"
        )


def _legacy_crsi(c: np.ndarray) -> np.ndarray:
    """Connors RSI with the streak of the original (non-nz) Pine helper: NaN before the
    first unchanged close, identical to the standard streak from there on."""
    streak = ind.updown_streak(c)
    equal = np.flatnonzero(c[1:] == c[:-1])
    streak[: (equal[0] + 1) if equal.size else len(c)] = np.nan
    prev = np.r_[np.nan, c[:-1]]
    return (ind.rsi(c, 3) + ind.rsi(streak, 2) + ind.percent_rank(100 * (c - prev) / prev, 100)) / 3


@pytest.mark.skipif(not FILES, reason=NO_FILES_REASON)
@pytest.mark.parametrize("path", FILES, ids=[p.name.removesuffix(".csv.gz") for p in FILES])
def test_F_0_4_2_golden_connors_rsi(path) -> None:
    """CONNORS_RSI_3_2_100 on the bars where the golden value is non-NaN.

    1. The golden column is reproduced exactly (NaN positions included) by our RSI, streak
       and percent-rank building blocks with the legacy streak start — every part is checked.
    2. Our standard (nz) Connors RSI has a value on every golden bar and equals the golden
       value within tolerance on every golden bar after a prefix right after the golden start
       where only the decaying RMA seed difference remains; that prefix is at most
       CRSI_SEED_DECAY_BARS long.
    """
    golden = load_golden(path)
    c = golden.columns["close"]
    ours, tv, tol = compare(golden, "CONNORS_RSI_3_2_100")
    has_tv = ~np.isnan(tv)
    assert has_tv.any()

    legacy = _legacy_crsi(c)
    np.testing.assert_array_equal(np.isnan(legacy), ~has_tv, err_msg="legacy NaN positions")
    assert np.all(np.abs(legacy[has_tv] - tv[has_tv]) <= tol[has_tv])

    assert not np.isnan(ours[has_tv]).any(), "NaN where TradingView has a value"
    idx = np.flatnonzero(has_tv)
    outside = np.flatnonzero(np.abs(ours[idx] - tv[idx]) > tol[idx])
    n_prefix = int(outside[-1]) + 1 if outside.size else 0  # all later bars are within tol
    assert n_prefix <= CRSI_SEED_DECAY_BARS, (
        f"{golden.name}: differences up to golden bar #{n_prefix} "
        f"(allowed seed decay: {CRSI_SEED_DECAY_BARS} bars)"
    )
