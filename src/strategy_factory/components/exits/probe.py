"""The fixed stage-1 probe exit signals (F-1.3; D-101, D-614).

Both rules return ``(long_exit, short_exit)``: a bool per bar, evaluated at the **close** of
bar ``i`` and filled at the open of ``i + 1`` (D-001). The engine adds the time cap
(``time_exit_bars``) and the 3-ATR disaster stop (D-130: on every probe, MR included).

* ``prev_extreme`` -- MR: a long exits when ``close > high[i-1]``, a short when
  ``close < low[i-1]`` (the mirror). Bar 0 has no previous bar and never exits.
* ``reverse`` -- TF: the **same probe's opposite-direction entry signal** (D-614): a long
  exits on the probe's short signal, a short on its long signal.

The parity harness keeps its **own** copy of ``close > high[1]``
(``selftest.parity_run.PARITY_EXIT_RULES``, D-370) and is not switched to this module
(D-614): the D-011 gate must keep running exactly what it ran. A test asserts the two are
equivalent on the parity fixtures.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

import numpy as np
import numpy.typing as npt

from strategy_factory.components.base import Bars, EntryComponent, ParamValue

BoolArray = npt.NDArray[np.bool_]
ExitRule = Literal["prev_extreme", "reverse"]


def prev_extreme(bars: Bars) -> tuple[BoolArray, BoolArray]:
    """MR probe exit: ``close > high[i-1]`` (long), ``close < low[i-1]`` (short)."""
    n = len(bars)
    long_exit = np.zeros(n, dtype=np.bool_)
    short_exit = np.zeros(n, dtype=np.bool_)
    long_exit[1:] = bars.close[1:] > bars.high[:-1]
    short_exit[1:] = bars.close[1:] < bars.low[:-1]
    return long_exit, short_exit


def reverse(
    probe: type[EntryComponent], bars: Bars, params: Mapping[str, ParamValue] | None = None
) -> tuple[BoolArray, BoolArray]:
    """TF probe exit: the probe's opposite-direction entry signal (long exit = short entry)."""
    long_entry, short_entry = probe.signals(bars, params)
    return np.asarray(short_entry, dtype=np.bool_), np.asarray(long_entry, dtype=np.bool_)


def probe_exit_signals(
    rule: ExitRule,
    probe: type[EntryComponent],
    bars: Bars,
    params: Mapping[str, ParamValue] | None = None,
) -> tuple[BoolArray, BoolArray]:
    """``(long_exit, short_exit)`` of ``rule`` for ``probe`` on ``bars``."""
    if rule == "prev_extreme":
        return prev_extreme(bars)
    if rule == "reverse":
        return reverse(probe, bars, params)
    raise ValueError(f"unknown probe exit rule {rule!r}")
