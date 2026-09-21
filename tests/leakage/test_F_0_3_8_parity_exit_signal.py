"""F-0.3.8 / CLAUDE.md rule 3: the parity exit signals see no future bar (D-370).

Every signal needs a data-truncation test: computing it on the bars up to ``t`` must give the
same value at every bar ``<= t`` as computing it on the full series. ``PARITY_EXIT_RULES`` is
where the parity harness keeps the Pine exit signals that have no registered component (the
MR script's ``close > high[1]``); every rule in it is checked here, so a rule added later is
checked automatically.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from strategy_factory.selftest.parity_refs import (
    ChartData,
    fixture,
    fixture_dir,
    load_chart_data,
    load_manifest,
)
from strategy_factory.selftest.parity_run import PARITY_EXIT_RULES

pytestmark = pytest.mark.leakage

#: the real MR chart -- the series the rule actually runs on in the gate
CHART = load_chart_data(fixture("BATS_SPY, 1D.csv"), load_manifest(fixture_dir()))


def head(chart: ChartData, t: int) -> ChartData:
    """The chart as it was known at the close of bar ``t - 1``."""
    return ChartData(
        name=chart.name,
        sha256=chart.sha256,
        ts=chart.ts[:t],
        open=chart.open[:t],
        high=chart.high[:t],
        low=chart.low[:t],
        close=chart.close[:t],
    )


@pytest.mark.parametrize("name", sorted(PARITY_EXIT_RULES))
@settings(max_examples=60, deadline=None)
@given(cut=st.integers(min_value=1, max_value=len(CHART)))
def test_F_0_3_8_parity_exit_signal_truncation_invariance(name: str, cut: int) -> None:
    rule = PARITY_EXIT_RULES[name]
    full = np.asarray(rule(CHART), dtype=bool)
    part = np.asarray(rule(head(CHART, cut)), dtype=bool)
    assert part.shape == (cut,)
    np.testing.assert_array_equal(part, full[:cut], err_msg=f"{name} looked ahead at cut {cut}")


@pytest.mark.parametrize("name", sorted(PARITY_EXIT_RULES))
def test_F_0_3_8_parity_exit_signal_is_not_vacuous(name: str) -> None:
    """A signal that is never true would pass any truncation test."""
    fired = np.asarray(PARITY_EXIT_RULES[name](CHART), dtype=bool)
    assert 0 < fired.sum() < fired.size
