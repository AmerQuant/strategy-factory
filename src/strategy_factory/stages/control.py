"""The random-walk control of stage 1 (D-615): a series' own returns, permuted.

For one (symbol, timeframe) the synthetic series keeps the **timestamps, the bar count and
each bar's own shape relative to its close** (the ratios ``open/close``, ``high/close`` and
``low/close``), and replaces the path of closes by a seeded **permutation of the series' own
bar-to-bar log returns**. That keeps the volatility and the drift and destroys every serial
dependence: whatever edge stage 1 finds on it is a false positive. Volume and every other
column are left as they are.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

Arrays = dict[str, npt.NDArray[Any]]


def permute_returns(bars: Arrays, seed: int) -> Arrays:
    """``bars`` with the close path rebuilt from its own permuted log returns (see above)."""
    close = np.asarray(bars["close"], dtype=np.float64)
    if close.size < 2:
        return dict(bars)
    log_ret = np.diff(np.log(close))
    shuffled = np.random.default_rng(seed).permutation(log_ret)
    new_close = close[0] * np.exp(np.concatenate(([0.0], np.cumsum(shuffled))))
    scale = new_close / close
    out = dict(bars)
    for col in ("open", "high", "low"):
        out[col] = np.asarray(bars[col], dtype=np.float64) * scale
    out["close"] = new_close
    return out
