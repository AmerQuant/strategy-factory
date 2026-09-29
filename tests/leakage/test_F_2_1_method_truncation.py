"""Rule 3 for stage 2 (T13 §9): every method's signals, in every cell, are truncation-invariant,
and so are the trades of the stage's own cell run (``method_run``, the function the stage calls).

A signal at bar i may use data up to the close of bar i only: the signals computed on the first
``t`` bars must equal the first ``t`` signals computed on the whole series.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from fixtures.edge_stage import synthetic_bars

from strategy_factory.components.base import Bars
from strategy_factory.components.registry import default_registry
from strategy_factory.core.config import EngineConfig
from strategy_factory.stages.screen import method_cells, method_run
from strategy_factory.stages.screen_config import load_s02_config

METHODS = sorted(
    (c for c in default_registry().entries() if getattr(c, "screen", False)), key=lambda c: c.name
)
DATA = synthetic_bars(500, 7, phi=-0.2)
BARS = Bars(DATA["open"], DATA["high"], DATA["low"], DATA["close"])
CUTS = (150, 260, 377, 499)


@pytest.mark.parametrize("comp", METHODS, ids=lambda c: c.name)
def test_F_2_1_method_signals_are_truncation_invariant(comp: Any) -> None:
    for params in method_cells(comp.name):
        full_long, full_short = comp.signals(BARS, params)
        for t in CUTS:
            lo, sh = comp.signals(BARS.head(t), params)
            assert np.array_equal(lo, full_long[:t]), (comp.name, params, t)
            assert np.array_equal(sh, full_short[:t]), (comp.name, params, t)


def _head(bars: dict[str, np.ndarray], t: int) -> dict[str, np.ndarray]:
    return {k: v[:t] for k, v in bars.items()}


@pytest.mark.parametrize(
    ("method", "direction"),
    [
        ("mr_rsi", "long"),
        ("mr_williams_confirm", "short"),
        ("mr_candle_score", "long"),
        ("tf_atr_band", "long"),
        ("tf_base_candle", "short"),
    ],
)
def test_F_2_1_the_stage_cell_run_is_truncation_invariant(method: str, direction: str) -> None:
    """Every trade that closes before the cut is identical in the truncated run."""
    cfg = load_s02_config()
    comp = default_registry().get(method)
    exits = cfg.exits[comp.edge_type]
    engine = EngineConfig()
    for params in method_cells(method)[:6]:
        full = method_run(DATA, method, params, exits, direction, engine)  # type: ignore[arg-type]
        for t in (220, 410):
            part = method_run(_head(DATA, t), method, params, exits, direction, engine)  # type: ignore[arg-type]
            done = full.exit_idx < t - 1  # closed strictly before the truncated series' last bar
            k = int(done.sum())
            assert np.array_equal(part.entry_idx[:k], full.entry_idx[done])
            assert np.array_equal(part.exit_idx[:k], full.exit_idx[done])
            assert np.allclose(part.pnl_net[:k], full.pnl_net[done])
