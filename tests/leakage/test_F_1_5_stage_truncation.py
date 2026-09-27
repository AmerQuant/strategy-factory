"""F-1.5 / CLAUDE.md rule 3: nothing stage 1 computes at bar t uses bar t+1.

The stage's own probe run (``stages.edge.probe_run``: the probe's signals, its fixed exits, the
engine, settings from ``EngineConfig``). For every probe and both directions, every trade that
**closed before the cut** is identical -- entry, exit, prices, ATR and its ATR return -- whether
the run sees the bars after the cut or not. **Scope, stated plainly:** this covers the probe
trades every statistic is computed from. The profile's aggregate statistics (means, percentile,
consistency) are functions of the whole development window by design, and the baseline's draws
are uniform over that window's bars -- they depend on its length, never on a price after the
bar a trade is decided at.
"""

from __future__ import annotations

import numpy as np
import pytest
from fixtures.edge_stage import stage_config, synthetic_bars

from strategy_factory.baseline.random_entries import atr_returns
from strategy_factory.core.config import EngineConfig
from strategy_factory.stages.edge import probe_params, probe_run

pytestmark = pytest.mark.leakage

CFG = stage_config()
ENGINE = EngineConfig()  # the research defaults: ATR length and disaster multiple from config
PROBES = sorted(CFG.probes)
FULL = synthetic_bars(900, 4, phi=-0.2)


def run(bars: dict, name: str, direction: str) -> tuple[dict, np.ndarray]:
    """Exactly what the stage runs for a probe: ``stages.edge.probe_run`` (zero costs)."""
    from strategy_factory.components.registry import default_registry

    edge_type = default_registry().get(name).edge_type
    params = probe_params(CFG, edge_type)[name]
    sim = probe_run(bars, name, params, CFG.edge_types[edge_type], direction, ENGINE)  # type: ignore[arg-type]
    d = 1 if direction == "long" else -1
    fields = {
        f: getattr(sim, f)
        for f in ("entry_idx", "exit_idx", "entry_price", "exit_price", "atr_at_entry")
    }
    return fields, atr_returns(sim, d)


@pytest.mark.parametrize("direction", ["long", "short"])
@pytest.mark.parametrize("name", PROBES)
def test_F_1_5_probe_trades_before_a_cut_do_not_see_past_it(name: str, direction: str) -> None:
    full, r_full = run(FULL, name, direction)
    checked = 0
    for cut in (150, 400, 777):
        head = {c: v[:cut] for c, v in FULL.items()}
        part, r_part = run(head, name, direction)
        done = full["exit_idx"] < cut - 1  # closed strictly inside the truncated window
        m = int(done.sum())
        for f in full:
            np.testing.assert_array_equal(part[f][:m], full[f][done], err_msg=f"{f} cut {cut}")
        np.testing.assert_array_equal(r_part[:m], r_full[done])
        checked += m
    assert checked > 0  # the probe traded before a cut: the check is not vacuous
