"""Stage 3's fine grid (T14 §2; F-3.1; D-120, D-639, D-640, D-649, D-650 (a), (b)).

Per numeric parameter: the range of stage 2's good region, widened by ``margin`` coarse steps on
each side -- the neighbouring coarse value; beyond the first or last coarse value, the end
coarse interval -- clipped to the parameter's ``[min, max]``, with values on
``min + i · fine_step`` (integer parameters: ``fine_step`` 1, D-640). The good region's bounds
come from the good cells that share the fixed choice values (the slice actually searched,
D-650 (b)). Choice parameters are fixed at the good-region median cell's values (D-640).

Above ``max_cells`` the lattice is **coarsened**, never Sobol-sampled (D-649): the step of the
axis with the most values is multiplied by 2, 3, … until the grid fits; the multipliers are
recorded.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from strategy_factory.components.base import ParamSpec
from strategy_factory.components.registry import default_registry
from strategy_factory.core.errors import ConfigError


@dataclass(frozen=True)
class FineGrid:
    method: str
    axes: dict[str, tuple[float | int, ...]]  # the numeric axes, in declaration order
    fixed: dict[str, Any]  # choice parameters (D-640)
    size_d639: int  # before any coarsening
    multipliers: dict[str, int]  # the step multiplier per axis (1 unless above the cap)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.axes)

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(len(v) for v in self.axes.values())

    @property
    def size(self) -> int:
        return math.prod(self.shape)

    def cells(self) -> list[dict[str, Any]]:
        """Every cell's parameters, in lattice order (C order over ``axes``)."""
        names = self.names
        return [
            {**dict(zip(names, vals, strict=True)), **self.fixed}
            for vals in itertools.product(*self.axes.values())
        ]


def _on_steps(spec: ParamSpec, lo: float, hi: float, step: float) -> tuple[float | int, ...]:
    assert spec.min is not None
    base = float(spec.min)
    i0 = math.ceil((lo - base) / step - 1e-9)
    i1 = math.floor((hi - base) / step + 1e-9)
    vals = [round(base + i * step, 10) for i in range(i0, i1 + 1)]
    if spec.kind == "int":
        return tuple(int(v) for v in vals)
    return tuple(vals)


def fine_axis(
    spec: ParamSpec, good_values: Sequence[float], margin: int = 1, multiplier: int = 1
) -> tuple[float | int, ...]:
    """D-639: one numeric axis from the good region's values (see the module docstring)."""
    if spec.kind == "choice" or spec.fine_step is None:
        raise ConfigError(f"{spec.name}: a choice parameter has no fine axis (D-640)")
    if not good_values:
        raise ConfigError(f"{spec.name}: the good region has no value")
    coarse = [float(v) for v in spec.coarse_values]
    lo_g, hi_g = min(good_values), max(good_values)
    try:
        i_lo, i_hi = coarse.index(float(lo_g)), coarse.index(float(hi_g))
    except ValueError as exc:
        raise ConfigError(f"{spec.name}: a good-region value is not a coarse value") from exc
    first, last = coarse[1] - coarse[0], coarse[-1] - coarse[-2]
    lo = coarse[i_lo - margin] if i_lo - margin >= 0 else coarse[0] - (margin - i_lo) * first
    top = len(coarse) - 1
    hi = (
        coarse[i_hi + margin] if i_hi + margin <= top else coarse[-1] + (i_hi + margin - top) * last
    )
    assert spec.min is not None and spec.max is not None
    lo, hi = max(lo, float(spec.min)), min(hi, float(spec.max))
    return _on_steps(spec, lo, hi, float(spec.fine_step) * multiplier)


def fine_grid(
    method: str,
    good_cells: Sequence[Mapping[str, Any]],
    median_cell: Mapping[str, Any],
    *,
    margin: int = 1,
    max_cells: int = 2000,
    max_free_params: int = 3,
) -> FineGrid:
    """The fine grid of ``method`` from stage 2's good region and its median cell."""
    comp = default_registry().get(method)
    choices = {p.name: median_cell[p.name] for p in comp.params if p.kind == "choice"}
    same = [g for g in good_cells if all(g[n] == v for n, v in choices.items())]
    if not same:
        raise ConfigError(f"{method}: no good-region cell shares the median cell's choices")
    numeric = [p for p in comp.params if p.kind != "choice"]
    if len(numeric) > max_free_params:
        raise ConfigError(f"{method}: {len(numeric)} free parameters > {max_free_params} (D-120)")
    good = {p.name: [float(g[p.name]) for g in same] for p in numeric}
    mult = {p.name: 1 for p in numeric}
    axes = {p.name: fine_axis(p, good[p.name], margin) for p in numeric}
    size_d639 = math.prod(len(v) for v in axes.values())
    while math.prod(len(v) for v in axes.values()) > max_cells:
        widest = max(axes, key=lambda n: (len(axes[n]), -list(axes).index(n)))
        if len(axes[widest]) <= 1:
            raise ConfigError(f"{method}: the grid cannot be coarsened below {max_cells} cells")
        mult[widest] += 1
        spec = next(p for p in numeric if p.name == widest)
        axes[widest] = fine_axis(spec, good[widest], margin, mult[widest])
    return FineGrid(method=method, axes=axes, fixed=choices, size_d639=size_d639, multipliers=mult)


__all__ = ["FineGrid", "fine_axis", "fine_grid"]
