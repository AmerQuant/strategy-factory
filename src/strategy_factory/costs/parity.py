"""Parity cost arrays from the Pine settings (T11 §3, **D-362**).

A parity run reproduces **TradingView**, so its costs are the Strategy Properties of the Pine
script and nothing else: never a Moneta profile, never the research assumptions. The broker
volume step and minimum volume do not apply in parity mode either (D-347).

What TradingView models, and how it maps onto :class:`~strategy_factory.costs.arrays.CostArrays`:

======================  ==================================================================
Pine setting            engine input
======================  ==================================================================
commission "percent"    commission kernel code 1 (rate x |qty| x price), per side
commission "per
contract"               code 2 (per share/contract, no minimum or maximum)
commission "per order"  code 4 (a fixed amount per side, D-319)
commission "none"       code 0
slippage (ticks)        ``slippage_fixed`` = ticks x tick size, on every fill
======================  ==================================================================

TradingView models **no spread** and **no swap**, so ``half_spread`` and both swap arrays are
zero and no bar is a rollover bar. That is not an omission: adding either would make the
comparison measure our cost model instead of the engine.
"""

from __future__ import annotations

import numpy as np

from strategy_factory.core.errors import ConfigError
from strategy_factory.core.parity_config import PineSettings
from strategy_factory.costs.arrays import CostArrays

#: Commission kernel codes (T06/T06b signature, mirrored in ``engine/commission.py``).
_CODES = {"none": 0, "percent": 1, "per_contract": 2, "per_order": 4}
PARITY_PROFILE = "tradingview_parity"


def commission_params(pine: PineSettings) -> tuple[int, float, float, float]:
    """The kernel's ``(code, p0, p1, p2)`` for the Pine commission settings (D-362)."""
    code = _CODES.get(pine.commission_type)
    if code is None:  # pragma: no cover - the Literal keeps this unreachable
        raise ConfigError(f"unknown commission type {pine.commission_type!r}")
    if code == 0:
        return (0, 0.0, 0.0, 0.0)
    if code == 1:
        # TradingView states a percent; the kernel takes a fraction of the traded value.
        return (1, pine.commission_value / 100.0, 0.0, 0.0)
    if code == 2:
        # per contract: no minimum, no maximum (TradingView applies neither).
        return (2, pine.commission_value, 0.0, np.inf)
    return (4, pine.commission_value, 0.0, 0.0)


def parity_cost_arrays(pine: PineSettings, n_bars: int) -> CostArrays:
    """Cost arrays for a parity run of ``n_bars`` bars, built from ``pine`` alone (D-362).

    No spread and no swap: TradingView models neither. Slippage is the Pine ticks converted to
    price units and applied to every fill. The volume step and minimum are 0-effect
    (``volume_step`` 0 is invalid, so they are set to values the parity sizing branch ignores,
    D-347).
    """
    if n_bars < 1:
        raise ConfigError("a parity run needs at least one bar")
    zeros = np.zeros(n_bars, dtype=np.float64)
    never = np.zeros(n_bars, dtype=np.bool_)
    return CostArrays(
        half_spread=zeros.copy(),  # TradingView models no spread
        slippage_fixed=np.full(n_bars, pine.slippage_price(), dtype=np.float64),
        slippage_atr_frac=0.0,  # TradingView's slippage is fixed ticks, not ATR-scaled
        swap_long_per_notional_day=zeros.copy(),  # no swap
        swap_short_per_notional_day=zeros.copy(),
        rollover_mask=never.copy(),
        triple_mask=never.copy(),
        commission_params=commission_params(pine),
        profile_name=PARITY_PROFILE,
        profile_status="verified",  # these are the reference's own settings, not a placeholder
        stress=1.0,
        commission_ccy="USD",
        quote_ccy="USD",
        contract_size=1.0,
        volume_step=1.0,  # ignored in parity sizing (D-347): the parity step is per run
        min_volume=1.0,  # ignored in parity sizing (D-347)
        volume_step_assumed=False,  # not assumed: parity does not use a broker step at all
        to_verify=(),
    )
