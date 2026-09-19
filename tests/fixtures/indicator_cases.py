"""Every public indicator as ``name -> f(open, high, low, close) -> tuple of arrays``.

Used by the leakage (truncation) tests so that each indicator output is covered, including the
helpers and non-default modes that the golden exports do not plot.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from strategy_factory.components import indicators as ind

Arr = np.ndarray
Case = Callable[[Arr, Arr, Arr, Arr], tuple[Arr, ...]]

INDICATOR_CASES: dict[str, Case] = {
    "sma": lambda o, h, lo, c: (ind.sma(c, 5),),
    "ema": lambda o, h, lo, c: (ind.ema(c, 5),),
    "rma": lambda o, h, lo, c: (ind.rma(c, 4),),
    "wma": lambda o, h, lo, c: (ind.wma(c, 6),),
    "hma": lambda o, h, lo, c: (ind.hma(c, 9),),
    "kama": lambda o, h, lo, c: (ind.kama(c, 10, 2, 30),),
    "sma_slope": lambda o, h, lo, c: (ind.sma_slope(c, 7),),
    "true_range": lambda o, h, lo, c: (
        ind.true_range(h, lo, c, True),
        ind.true_range(h, lo, c, False),
    ),
    "atr": lambda o, h, lo, c: (ind.atr(h, lo, c, 14),),
    "stdev": lambda o, h, lo, c: (ind.stdev(c, 10),),
    "bollinger": lambda o, h, lo, c: tuple(ind.bollinger(c, 20, 2.0)),
    "keltner": lambda o, h, lo, c: tuple(ind.keltner(h, lo, c, 20, 2.0)),
    "keltner_hl": lambda o, h, lo, c: tuple(ind.keltner(h, lo, c, 10, 1.5, False)),
    "highest": lambda o, h, lo, c: (ind.highest(h, 10),),
    "lowest": lambda o, h, lo, c: (ind.lowest(c, 7),),
    "highest_bars": lambda o, h, lo, c: (ind.highest_bars(h, 8),),
    "lowest_bars": lambda o, h, lo, c: (ind.lowest_bars(lo, 8),),
    "donchian": lambda o, h, lo, c: tuple(ind.donchian(h, lo, 20)),
    "rsi": lambda o, h, lo, c: (ind.rsi(c, 2), ind.rsi(c, 14)),
    "ibs": lambda o, h, lo, c: (ind.ibs(h, lo, c),),
    "zscore": lambda o, h, lo, c: (ind.zscore(c, 20),),
    "macd": lambda o, h, lo, c: tuple(ind.macd(c, 12, 26, 9)),
    "roc": lambda o, h, lo, c: (ind.roc(c, 20),),
    "momentum": lambda o, h, lo, c: (ind.momentum(c, 20),),
    "williams_r": lambda o, h, lo, c: (ind.williams_r(h, lo, c, 14),),
    "stochastic": lambda o, h, lo, c: tuple(ind.stochastic(h, lo, c, 14, 3, 3)),
    "percent_rank": lambda o, h, lo, c: (ind.percent_rank(c, 10),),
    "updown_streak": lambda o, h, lo, c: (ind.updown_streak(c),),
    "connors_rsi": lambda o, h, lo, c: (ind.connors_rsi(c, 3, 2, 20),),
    "dmi": lambda o, h, lo, c: tuple(ind.dmi(h, lo, c, 14, 14)),
    "supertrend": lambda o, h, lo, c: tuple(ind.supertrend(h, lo, c, 3.0, 10)),
    "psar": lambda o, h, lo, c: (ind.psar(h, lo, c, 0.02, 0.02, 0.2),),
    "aroon": lambda o, h, lo, c: tuple(ind.aroon(h, lo, 25)),
    "ichimoku": lambda o, h, lo, c: tuple(ind.ichimoku(h, lo, 9, 26, 52)),
}


def random_ohlc(
    seed: int, n: int, *, flat_prob: float = 0.1, start: float = 100.0
) -> tuple[Arr, Arr, Arr, Arr]:
    """Valid positive OHLC random walk; with probability ``flat_prob`` a bar repeats the
    previous close and/or is a zero-range bar, so ties and flat windows occur."""
    rng = np.random.default_rng(seed)
    close = np.empty(n)
    open_ = np.empty(n)
    high = np.empty(n)
    low = np.empty(n)
    prev = start
    for i in range(n):
        o = prev
        c = prev if rng.random() < flat_prob else prev * float(np.exp(rng.normal(0.0, 0.02)))
        if rng.random() < flat_prob:
            o = c
            h = lo = c
        else:
            h = max(o, c) * (1.0 + abs(rng.normal(0.0, 0.01)))
            lo = min(o, c) * (1.0 - abs(rng.normal(0.0, 0.01)))
        open_[i], high[i], low[i], close[i] = o, h, lo, c
        prev = c
    return open_, high, low, close
