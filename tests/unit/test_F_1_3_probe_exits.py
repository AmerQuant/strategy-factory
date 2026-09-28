"""F-1.3 (D-101, D-614): the fixed probe exits behave as defined, and the stage's MR rule is
equivalent to the parity harness's own copy on the parity fixtures."""

from __future__ import annotations

import numpy as np
import pytest

from strategy_factory.components.base import Bars
from strategy_factory.components.exits.probe import (
    prev_extreme,
    probe_exit_signals,
    reverse,
)
from strategy_factory.components.registry import default_registry
from strategy_factory.selftest.parity_refs import (
    fixture,
    fixture_dir,
    load_chart_data,
    load_manifest,
)
from strategy_factory.selftest.parity_run import PARITY_EXIT_RULES


def bars(high: list[float], low: list[float], close: list[float]) -> Bars:
    c = np.array(close)
    return Bars(c.copy(), np.array(high), np.array(low), c)


def test_F_1_3_prev_extreme_hand_case() -> None:
    b = bars(
        high=[10.0, 11.0, 12.0, 12.0],
        low=[9.0, 10.0, 11.0, 10.0],
        close=[9.5, 10.5, 11.5, 9.9],
    )
    long_exit, short_exit = prev_extreme(b)
    # bar 1: 10.5 > high[0] 10 -> long exit; bar 2: 11.5 > 11; bar 3: 9.9 > 12? no
    assert long_exit.tolist() == [False, True, True, False]
    # bar 3: 9.9 < low[2] 11 -> short exit; bar 1: 10.5 < 9? no
    assert short_exit.tolist() == [False, False, False, True]


def test_F_1_3_prev_extreme_is_strict_and_bar_zero_never_exits() -> None:
    b = bars(high=[10.0, 10.0], low=[9.0, 9.0], close=[9.5, 10.0])  # close == prev high
    long_exit, short_exit = prev_extreme(b)
    assert not long_exit.any() and not short_exit.any()


def test_F_1_3_prev_extreme_short_is_the_mirror_of_long() -> None:
    rng = np.random.default_rng(3)
    c = 100 + rng.normal(0, 1, 300).cumsum()
    b = Bars(c, c + rng.uniform(0.1, 1, 300), c - rng.uniform(0.1, 1, 300), c)
    _, short_exit = prev_extreme(b)
    long_m, _ = prev_extreme(b.mirrored())
    np.testing.assert_array_equal(short_exit, long_m)


def test_F_1_3_reverse_is_the_probes_opposite_signal() -> None:
    probe = default_registry().get("tf_donchian20_breakout")
    rng = np.random.default_rng(5)
    c = 100 + rng.normal(0, 1, 400).cumsum()
    b = Bars(c, c + 0.5, c - 0.5, c)
    long_entry, short_entry = probe.signals(b)
    long_exit, short_exit = reverse(probe, b)
    np.testing.assert_array_equal(long_exit, short_entry)
    np.testing.assert_array_equal(short_exit, long_entry)
    assert long_exit.any() and short_exit.any()  # not vacuous


def test_F_1_3_the_rule_dispatch() -> None:
    probe = default_registry().get("tf_donchian20_breakout")
    b = bars(high=[10.0, 11.0], low=[9.0, 10.0], close=[9.5, 10.5])
    for rule in ("prev_extreme", "reverse"):
        out = probe_exit_signals(rule, probe, b)  # type: ignore[arg-type]
        assert len(out) == 2 and out[0].dtype == np.bool_
    with pytest.raises(ValueError, match="unknown probe exit rule"):
        probe_exit_signals("nope", probe, b)  # type: ignore[arg-type]


# -- D-614: the parity harness keeps its own copy; the two must agree -------------------------
@pytest.mark.parametrize("chart_name", ["BATS_SPY, 1D.csv", "OANDA_XAUUSD, 60.csv"])
def test_F_1_3_d614_the_stage_rule_equals_the_parity_harness_copy(chart_name: str) -> None:
    chart = load_chart_data(fixture(chart_name), load_manifest(fixture_dir()))
    harness = PARITY_EXIT_RULES["close_above_prev_high"](chart)
    ours, _ = prev_extreme(Bars(chart.open, chart.high, chart.low, chart.close))
    np.testing.assert_array_equal(ours, harness)
    assert harness.sum() > 100  # the rule fires on real data: the comparison is not vacuous
