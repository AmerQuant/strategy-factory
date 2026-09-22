"""F-1.5 / CLAUDE.md rule 3: nothing stage 1 computes at bar t uses bar t+1.

A probe run is the probe's signals, its fixed exits and the engine. For every probe and both
directions, every trade that **closed before the cut** is identical -- entry, exit, prices,
ATR and its ATR return -- whether the run sees the bars after the cut or not. The baseline
draws depend on the length of the window by construction (they are uniform over it), not on
any future price.
"""

from __future__ import annotations

import numpy as np
import pytest
from fixtures.edge_stage import stage_config, synthetic_bars

from strategy_factory.baseline.random_entries import (
    atr_returns,
    frictionless_costs,
    frictionless_sizing,
)
from strategy_factory.components.base import Bars
from strategy_factory.components.exits.probe import probe_exit_signals
from strategy_factory.components.registry import default_registry
from strategy_factory.engine import kernel as k
from strategy_factory.engine.api import ExitParams, simulate
from strategy_factory.pipeline.backtest import market_arrays

pytestmark = pytest.mark.leakage

CFG = stage_config()
PROBES = sorted(CFG.probes)
FULL = synthetic_bars(900, 4, phi=-0.2)


def probe_run(bars: dict, name: str, direction: str) -> tuple[dict, np.ndarray]:
    comp = default_registry().get(name)
    spec = CFG.edge_types[comp.edge_type]
    b = Bars(*(bars[c] for c in ("open", "high", "low", "close")))
    long_e, short_e = comp.signals(b)
    long_x, short_x = probe_exit_signals(spec.exit_signal, comp, b)
    d = 1 if direction == "long" else -1
    n = len(b)
    sim = simulate(
        market_arrays(bars, 14),
        long_e if d == 1 else short_e,
        long_x if d == 1 else short_x,
        d,
        ExitParams(time_exit_bars=spec.time_exit_bars, disaster_atr=3.0),
        frictionless_costs(n),
        frictionless_sizing(100_000.0, 100_000.0),
        k.MODE_PESSIMISTIC,
    )
    fields = {
        f: getattr(sim, f)
        for f in ("entry_idx", "exit_idx", "entry_price", "exit_price", "atr_at_entry")
    }
    return fields, atr_returns(sim, d)


@pytest.mark.parametrize("direction", ["long", "short"])
@pytest.mark.parametrize("name", PROBES)
def test_F_1_5_probe_trades_before_a_cut_do_not_see_past_it(name: str, direction: str) -> None:
    full, r_full = probe_run(FULL, name, direction)
    checked = 0
    for cut in (150, 400, 777):
        head = {c: v[:cut] for c, v in FULL.items()}
        part, r_part = probe_run(head, name, direction)
        done = full["exit_idx"] < cut - 1  # closed strictly inside the truncated window
        m = int(done.sum())
        for f in full:
            np.testing.assert_array_equal(part[f][:m], full[f][done], err_msg=f"{f} cut {cut}")
        np.testing.assert_array_equal(r_part[:m], r_full[done])
        checked += m
    assert checked > 0  # the probe traded before a cut: the check is not vacuous
