"""F-3.1 / D-639 / D-640 / D-649 / D-650 (a), (b): stage 3's fine grid (T14 §7)."""

from __future__ import annotations

import pytest

from strategy_factory.components.base import ParamSpec
from strategy_factory.core.errors import ConfigError
from strategy_factory.stages.optimize_config import load_s03_config
from strategy_factory.stages.optimize_grid import fine_axis, fine_grid

_FG = load_s03_config().fine_grid  # the shipped config's values (D-639, D-120)
LIMITS = {
    "margin": _FG.margin_coarse_steps,
    "max_cells": _FG.max_cells,
    "max_free_params": _FG.max_free_params,
}


def spec(
    coarse: tuple[float, ...], lo: float, hi: float, step: float, kind: str = "int"
) -> ParamSpec:
    return ParamSpec(
        name="p",
        kind=kind,  # type: ignore[arg-type]
        default=coarse[0],
        min=lo,
        max=hi,
        coarse_values=coarse,
        fine_step=step,
    )


def test_F_3_1_d639_margin_is_the_neighbouring_coarse_value() -> None:
    s = spec((3, 5, 10, 20), 2, 100, 1)
    assert fine_axis(s, [5, 10], 1) == tuple(range(3, 21))  # 3 .. 20: one coarse step each side
    assert fine_axis(s, [10], 1) == tuple(range(5, 21))


def test_F_3_1_d639_beyond_the_ends_the_end_interval_then_clipping() -> None:
    s = spec((3, 5, 10, 20), 2, 100, 1)
    assert fine_axis(s, [20], 1) == tuple(range(10, 31))  # 20 + (20 - 10)
    assert fine_axis(s, [3], 1) == (2, 3, 4, 5)  # 3 - (5 - 3) = 1, clipped to min 2
    tight = spec((3, 5, 10, 20), 2, 25, 1)
    assert fine_axis(tight, [20], 1)[-1] == 25  # clipped to max


def test_F_3_1_d639_float_steps_on_the_parameter_lattice() -> None:
    s = spec((0.25, 0.5, 0.75, 1.0), 0.05, 5.0, 0.05, kind="float")
    ax = fine_axis(s, [0.5], 1)
    assert ax[0] == pytest.approx(0.25) and ax[-1] == pytest.approx(0.75) and len(ax) == 11
    assert all(isinstance(v, float) for v in ax)


def test_F_3_1_d640_integers_at_integer_resolution() -> None:
    s = spec((1, 2, 3, 4), 1, 8, 1)
    ax = fine_axis(s, [3], 1)
    assert ax == (2, 3, 4) and all(isinstance(v, int) for v in ax)


def test_F_3_1_d640_choice_parameters_are_fixed_at_the_median_cell() -> None:
    """mr_williams_confirm: n, t numeric, confirm a choice (D-633). Good cells with another
    choice value do not widen the searched slice (D-650 (b))."""
    good = [
        {"confirm": "same_bar", "n": 20, "t": 20.0},
        {"confirm": "off", "n": 5, "t": 5.0},  # another choice: ignored for the bounds
    ]
    g = fine_grid(
        "mr_williams_confirm", good, {"confirm": "same_bar", "n": 20, "t": 20.0}, **LIMITS
    )
    assert g.fixed == {"confirm": "same_bar"}
    assert g.names == ("n", "t")
    assert g.axes["n"][0] == 14 and g.axes["n"][-1] == 26  # 20 +- one coarse step (14, 20+6)
    assert g.axes["t"][0] == 10.0 and g.axes["t"][-1] == 30.0
    assert all(c["confirm"] == "same_bar" for c in g.cells())
    assert g.size == len(g.cells()) == g.size_d639


def test_F_3_1_d649_above_the_cap_the_lattice_is_coarsened_deterministically() -> None:
    good = [
        {"conversion": 7, "base": 22, "span_b": 44},
        {"conversion": 15, "base": 40, "span_b": 80},
    ]
    med = {"conversion": 9, "base": 26, "span_b": 60}
    a = fine_grid("tf_ichimoku", good, med, **LIMITS)
    b = fine_grid("tf_ichimoku", good, med, **LIMITS)
    assert a == b  # deterministic
    assert a.size <= 2000 < a.size_d639
    assert any(m > 1 for m in a.multipliers.values())
    full = fine_grid("tf_ichimoku", good, med, **{**LIMITS, "max_cells": 10**9})
    assert full.size == a.size_d639 and set(full.multipliers.values()) == {1}


def test_F_3_1_d120_more_than_three_free_parameters_is_refused() -> None:
    good = [{"n": 10, "k": 2.0, "m": 14}]
    with pytest.raises(ConfigError, match="D-120"):
        fine_grid("tf_atr_band", good, good[0], **{**LIMITS, "max_free_params": 2})


def test_F_3_1_a_good_value_off_the_coarse_grid_is_refused() -> None:
    with pytest.raises(ConfigError, match="coarse value"):
        fine_axis(spec((3, 5, 10, 20), 2, 100, 1), [7], 1)
