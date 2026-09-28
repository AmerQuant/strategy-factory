"""D-615: the baseline draws signal bars from each probe's warm-up on; the configured
``warmup_bars`` must be exact -- no probe ever signals before it (so no allowed bar is
missed), and some series makes it signal right at it (so none is wasted)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fixtures.indicator_cases import random_ohlc

from strategy_factory.components.base import Bars
from strategy_factory.components.registry import default_registry
from strategy_factory.stages.config import DEFAULT_PATH, load_s01_config

REPO = Path(__file__).resolve().parents[2]
CFG = load_s01_config(REPO / DEFAULT_PATH)
PROBES = sorted(CFG.probes)


def earliest_signal(probe: str, seeds: range) -> int:
    comp = default_registry().get(probe)
    first = 10**9
    for seed in seeds:
        long_, short = comp.signals(Bars(*random_ohlc(seed, 200)))
        idx = np.flatnonzero(long_ | short)
        if idx.size:
            first = min(first, int(idx[0]))
    return first


@pytest.mark.parametrize("probe", PROBES)
def test_F_1_4_no_probe_signals_before_its_warmup(probe: str) -> None:
    assert earliest_signal(probe, range(300)) >= CFG.probes[probe].warmup_bars


@pytest.mark.slow
@pytest.mark.parametrize("probe", PROBES)
def test_F_1_4_the_warmup_is_tight(probe: str) -> None:
    """Measured over 3,000 random walks: the earliest signal is exactly the warm-up."""
    assert earliest_signal(probe, range(3000)) == CFG.probes[probe].warmup_bars
