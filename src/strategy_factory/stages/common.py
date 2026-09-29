"""Helpers every research stage shares (T15a plan §8, calibration item 9).

Stages 2 and 3 used stage 1's private ``_cost_arrays`` and ``_require_research_engine`` (whose
message said "stage 1" in every stage); they live here under public names, and the research-engine
check names the stage that calls it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from strategy_factory.core.errors import ConfigError
from strategy_factory.costs.arrays import CostArrays, build_cost_arrays, resolve_from_data
from strategy_factory.costs.profile import SpreadBrokerScaled, SpreadFromData, resolve_profile
from strategy_factory.stages.base import RunContext


class UnsupportedSymbol(Exception):
    """A symbol a research stage cannot run yet: listed as skipped with the reason, never aborts."""


def cost_arrays(
    symbol: str,
    asset_class: str,
    timeframe: str,
    bars: dict[str, np.ndarray],
    costs_dir: Path,
    profiles: Any,
    assignments: Any,
) -> CostArrays:
    """The symbol's cost arrays over ``bars`` (the development segment, D-340)."""
    profile = resolve_profile(symbol, asset_class, profiles, assignments, costs_dir)
    if isinstance(profile.spread, SpreadFromData | SpreadBrokerScaled):
        profile, _ = resolve_from_data(profile, bars)  # development bars only (D-340)
    costs = build_cost_arrays(bars, profile, timeframe=timeframe)
    if costs.quote_ccy != "USD":
        raise UnsupportedSymbol(
            f"quote currency {costs.quote_ccy}: the research stages run USD-quoted symbols only "
            "for now (no conversion arrays are wired in; P-105)"
        )
    return costs


def require_research_engine(ctx: RunContext, stage: str) -> None:
    """D-354 (1): the engine settings come from the run's config -- and the research stages
    refuse a parity setting rather than silently ignore it."""
    problems = []
    if ctx.config.intrabar_mode != "pessimistic":
        problems.append(f"intrabar_mode {ctx.config.intrabar_mode!r} (research runs 'pessimistic')")
    if ctx.config.engine.entry_requires_flat_at_signal:
        problems.append("engine.entry_requires_flat_at_signal (a parity-only option, D-367)")
    if problems:
        raise ConfigError(
            f"{stage} runs research settings only; the config sets " + "; ".join(problems)
        )
