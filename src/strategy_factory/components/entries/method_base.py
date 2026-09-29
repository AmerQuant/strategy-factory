"""What every stage-2 method shares (T13 §4; T15a plan §8, calibration item 9).

The mean-reversion and trend-following method modules (``methods_mr``, ``methods_tf``) both build
on :class:`Method` and the parameter helpers here. They lived in ``methods_mr`` as private names
that ``methods_tf`` imported; this module gives them a public home.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

import numpy as np

from strategy_factory.components.base import EntryComponent, FloatArray, ParamSpec, ParamValue


def prev(x: FloatArray, periods: int = 1) -> FloatArray:
    """Pine ``x[periods]``: NaN before the start."""
    out = np.full(x.shape[0], np.nan)
    if 0 < periods < x.shape[0]:
        out[periods:] = x[:-periods]
    return out


def int_value(p: Mapping[str, ParamValue], key: str) -> int:
    return int(p[key])


def float_value(p: Mapping[str, ParamValue], key: str) -> float:
    return float(p[key])


def int_param(name: str, default: int, coarse: tuple[int, ...], lo: int, hi: int) -> ParamSpec:
    return ParamSpec(
        name=name, kind="int", default=default, min=lo, max=hi, coarse_values=coarse, fine_step=1
    )


def float_param(
    name: str, default: float, coarse: tuple[float, ...], lo: float, hi: float, step: float
) -> ParamSpec:
    return ParamSpec(
        name=name,
        kind="float",
        default=default,
        min=lo,
        max=hi,
        coarse_values=coarse,
        fine_step=step,
    )


def choice_param(name: str, default: str, options: tuple[str, ...]) -> ParamSpec:
    return ParamSpec(name=name, kind="choice", default=default, coarse_values=options)


class Method(EntryComponent):
    """A stage-2 method (T13): an entry with a coarse grid and a declared warm-up."""

    screen: ClassVar[bool] = True

    @classmethod
    def warmup(cls, params: Mapping[str, ParamValue]) -> int:
        """First bar index at which the method can signal for resolved ``params``."""
        raise NotImplementedError
