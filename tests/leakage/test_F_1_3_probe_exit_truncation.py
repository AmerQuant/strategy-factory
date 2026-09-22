"""F-1.3 / CLAUDE.md rule 3: the stage-1 probe exit signals see no future bar.

Computing a rule on the bars up to ``t`` must give the same value at every bar ``< t`` as
computing it on the full series -- for ``prev_extreme`` and for ``reverse`` with every TF
probe (and, for completeness, every probe of the battery).
"""

from __future__ import annotations

import numpy as np
import pytest
from fixtures.indicator_cases import random_ohlc

from strategy_factory.components.base import Bars
from strategy_factory.components.exits.probe import probe_exit_signals
from strategy_factory.components.registry import default_registry

pytestmark = pytest.mark.leakage

PROBES = sorted(c.name for c in default_registry().entries() if c.group)
CUTS = (1, 2, 30, 77, 150, 299)


@pytest.mark.parametrize("rule", ["prev_extreme", "reverse"])
@pytest.mark.parametrize("probe_name", PROBES)
def test_F_1_3_probe_exits_are_truncation_invariant(rule: str, probe_name: str) -> None:
    probe = default_registry().get(probe_name)
    for seed in (1, 2, 3):
        full = Bars(*random_ohlc(seed, 300))
        long_full, short_full = probe_exit_signals(rule, probe, full)  # type: ignore[arg-type]
        for t in CUTS:
            long_t, short_t = probe_exit_signals(rule, probe, full.head(t))  # type: ignore[arg-type]
            np.testing.assert_array_equal(long_t, long_full[:t], err_msg=f"{seed} {t}")
            np.testing.assert_array_equal(short_t, short_full[:t], err_msg=f"{seed} {t}")


def test_F_1_3_a_look_ahead_rule_fails_the_truncation_check() -> None:
    """Non-vacuity: a one-bar look-ahead (``close[i+1] > close[i]``) is caught by the same check.

    (``close > high[i+1]`` would not do: these walks open at the previous close, so it never fires.)
    """
    full = Bars(*random_ohlc(9, 300))

    def peek(b: Bars) -> np.ndarray:
        out = np.zeros(len(b), dtype=np.bool_)
        out[:-1] = b.close[1:] > b.close[:-1]
        return out

    whole = peek(full)
    assert any(not np.array_equal(peek(full.head(t)), whole[:t]) for t in CUTS)
