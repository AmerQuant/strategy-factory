"""F-0.4.2 / F-0.3.9: data-truncation (look-ahead) tests for every indicator and probe.

For every indicator output and every registered probe, the values on bars ``0..t`` computed
from ``bars[0..t]`` must equal the values on bars ``0..t`` computed from the full series,
exactly (NaN positions included), for every ``t``.
"""

from __future__ import annotations

import numpy as np
import pytest
from fixtures.indicator_cases import INDICATOR_CASES, random_ohlc

from strategy_factory.components.base import Bars
from strategy_factory.components.registry import default_registry

pytestmark = pytest.mark.leakage

N_BARS = 180
SEEDS = (1, 2)


def _series(seed: int) -> tuple[np.ndarray, ...]:
    return random_ohlc(seed, N_BARS, flat_prob=0.15)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("name", sorted(INDICATOR_CASES))
def test_F_0_4_2_indicator_truncation_invariant(name: str, seed: int) -> None:
    o, h, lo, c = _series(seed)
    fn = INDICATOR_CASES[name]
    full = fn(o, h, lo, c)
    for t in range(1, N_BARS + 1):
        part = fn(o[:t], h[:t], lo[:t], c[:t])
        for k, (p, f) in enumerate(zip(part, full, strict=True)):
            np.testing.assert_array_equal(p, f[:t], err_msg=f"{name}[{k}] differs at t={t}")


PROBES = default_registry().entries()


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("probe", PROBES, ids=[p.name for p in PROBES])
def test_F_0_4_2_probe_truncation_invariant(probe, seed: int) -> None:
    bars = Bars(*_series(seed))
    full_long, full_short = probe.signals(bars)
    for t in range(1, N_BARS + 1):
        long_, short = probe.signals(bars.head(t))
        np.testing.assert_array_equal(long_, full_long[:t], err_msg=f"long at t={t}")
        np.testing.assert_array_equal(short, full_short[:t], err_msg=f"short at t={t}")


def test_F_0_4_2_truncation_cases_cover_every_public_indicator() -> None:
    from strategy_factory.components import indicators

    functions = {n for n in indicators.__all__ if callable(getattr(indicators, n)) and n.islower()}
    assert functions == set(INDICATOR_CASES) - {"keltner_hl"}
