"""F-0.4.1: component interface, parameter declarations and the component registry."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pytest
from pydantic import ValidationError

from strategy_factory.components.base import (
    Bars,
    BoolArray,
    Component,
    ComponentError,
    EntryComponent,
    ExitComponent,
    ExitSpec,
    GridRules,
    ParamSpec,
    ParamValue,
    check_param_grid,
    coarse_cells,
    resolve_params,
)
from strategy_factory.components.edges import load_edge_types
from strategy_factory.components.registry import ComponentRegistry, default_registry

MR_PROBES = {
    "mr_rsi2_below_10",
    "mr_rsi5_below_30",
    "mr_ibs_below_0_2",
    "mr_close_below_bb_lower",
    "mr_donchian20_new_low",
    "mr_zscore_below_minus_2",
    "mr_lowest_close_7",
    "mr_three_down_closes",
    "mr_macd_hist_trough_5",
}
TF_PROBES = {
    "tf_ma50_slope_up",
    "tf_sma_cross_20_100",
    "tf_donchian20_breakout",
    "tf_donchian55_breakout",
    "tf_close_above_bb_upper",
    "tf_supertrend_flip",
    "tf_ichimoku_cloud",
    "tf_roc20_cross_zero",
}


def int_param(name: str = "length", coarse: tuple[int, ...] = (5, 10, 15, 20)) -> ParamSpec:
    return ParamSpec(
        name=name, kind="int", default=10, min=1, max=50, coarse_values=coarse, fine_step=1
    )


def bars(n: int = 60, seed: int = 0) -> Bars:
    rng = np.random.default_rng(seed)
    c = 100.0 + np.cumsum(rng.normal(size=n))
    return Bars(c, c + 1.0, c - 1.0, c)


def make_entry(name: str, params: tuple[ParamSpec, ...] = (), **attrs: object) -> type:
    def long_signals(cls: type, b: Bars, p: Mapping[str, ParamValue]) -> BoolArray:
        return b.close > b.open

    body: dict[str, object] = {
        "name": name,
        "edge_type": "MR",
        "params": params,
        "long_signals": classmethod(long_signals),
        **attrs,
    }
    return type(name.title().replace("_", ""), (EntryComponent,), body)


# ----------------------------------------------------------------------------- registry


def test_F_0_4_1_registry_lookup_and_listing() -> None:
    reg = default_registry()
    assert set(reg.names()) >= MR_PROBES | TF_PROBES
    assert reg.get("mr_rsi2_below_10").name == "mr_rsi2_below_10"
    entries = {c.name for c in reg.list_by_role("entry")}
    assert entries == MR_PROBES | TF_PROBES
    assert reg.list_by_role("exit") == []
    edges = load_edge_types()
    assert {c.name for c in reg.list_by_edge_type("MR", edges)} == MR_PROBES
    assert {c.name for c in reg.list_by_edge_type("TF", edges)} == TF_PROBES
    assert reg.list_by_edge_type("SEASONAL", edges) == []
    for cls in reg.entries():
        assert isinstance(cls, Component)
    with pytest.raises(ComponentError, match="unknown component"):
        reg.get("no_such_method")
    with pytest.raises(ComponentError, match="unknown role"):
        reg.list_by_role("banana")  # type: ignore[arg-type]


def test_F_0_4_1_probe_defaults_are_the_spec_values() -> None:
    reg = default_registry()

    def defaults(name: str) -> dict[str, ParamValue]:
        return {p.name: p.default for p in reg.get(name).params}

    assert defaults("mr_rsi2_below_10") == {"length": 2, "threshold": 10.0}
    assert defaults("mr_rsi5_below_30") == {"length": 5, "threshold": 30.0}
    assert defaults("mr_ibs_below_0_2") == {"threshold": 0.2}
    assert defaults("mr_close_below_bb_lower") == {"length": 20, "mult": 2.0}
    assert defaults("mr_donchian20_new_low") == {"length": 20}
    assert defaults("mr_zscore_below_minus_2") == {"length": 20, "threshold": 2.0}
    assert defaults("mr_lowest_close_7") == {"length": 7}
    assert defaults("mr_three_down_closes") == {"count": 3}
    assert defaults("mr_macd_hist_trough_5") == {"window": 5}
    assert defaults("tf_ma50_slope_up") == {"length": 50}
    assert defaults("tf_sma_cross_20_100") == {"fast": 20, "slow": 100}
    assert defaults("tf_donchian20_breakout") == {"length": 20}
    assert defaults("tf_donchian55_breakout") == {"length": 55}
    assert defaults("tf_close_above_bb_upper") == {"length": 20, "mult": 2.0}
    assert defaults("tf_supertrend_flip") == {"atr_period": 10, "factor": 3.0}
    assert defaults("tf_ichimoku_cloud") == {"conversion": 9, "base": 26, "span_b": 52}
    assert defaults("tf_roc20_cross_zero") == {"length": 20}


def test_F_0_4_1_every_registered_component_respects_the_grid_rule() -> None:
    for name in default_registry().names():
        params = default_registry().get(name).params
        check_param_grid(params)
        assert coarse_cells(params) <= GridRules().max_coarse_cells


def test_F_0_4_1_duplicate_and_invalid_registrations_raise() -> None:
    reg = ComponentRegistry()
    reg.register(make_entry("dummy_a"))
    with pytest.raises(ComponentError, match="already registered"):
        reg.register(make_entry("dummy_a"))
    with pytest.raises(ComponentError, match="role"):
        reg.register(make_entry("dummy_b", role="exotic"))
    with pytest.raises(ComponentError, match="edge_type"):
        reg.register(make_entry("dummy_c", edge_type=""))
    with pytest.raises(ComponentError, match="directions"):
        reg.register(make_entry("dummy_d", directions=("up",)))
    with pytest.raises(ComponentError, match="directions"):
        reg.register(make_entry("dummy_e", directions=()))

    class NoName(EntryComponent):
        edge_type = "MR"

        @classmethod
        def long_signals(cls, b: Bars, p: Mapping[str, ParamValue]) -> BoolArray:
            return b.close > 0

    with pytest.raises(ComponentError, match="missing component name"):
        reg.register(NoName)
    assert reg.names() == ["dummy_a"]


# ----------------------------------------------------------------------------- ParamSpec


@pytest.mark.parametrize("coarse", [(5, 10, 15), (5, 10, 15, 20, 25), ()])
def test_F_0_4_1_param_spec_requires_exactly_four_coarse_values(coarse: tuple[int, ...]) -> None:
    with pytest.raises(ValidationError, match="exactly 4 coarse values"):
        int_param(coarse=coarse)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"coarse_values": (5, 5, 10, 15)}, "strictly increasing"),
        ({"coarse_values": (20, 15, 10, 5)}, "strictly increasing"),
        ({"default": 99}, r"\[min, max\]"),
        ({"coarse_values": (0, 5, 10, 15)}, r"\[min, max\]"),
        ({"min": 60}, "min > max"),
        ({"fine_step": 0}, "fine_step"),
        ({"fine_step": None}, "fine_step"),
        ({"coarse_values": (5, 10.5, 15, 20)}, "integral"),
        ({"name": "Bad Name"}, "snake_case"),
    ],
)
def test_F_0_4_1_param_spec_validation(kwargs: dict[str, object], match: str) -> None:
    base: dict[str, object] = {
        "name": "length",
        "kind": "int",
        "default": 10,
        "min": 1,
        "max": 50,
        "coarse_values": (5, 10, 15, 20),
        "fine_step": 1,
    }
    with pytest.raises(ValidationError, match=match):
        ParamSpec.model_validate({**base, **kwargs})


def test_F_0_4_1_choice_param_spec() -> None:
    spec = ParamSpec(
        name="ma_type", kind="choice", default="sma", coarse_values=("sma", "ema", "hma", "wma")
    )
    assert spec.coerce("ema") == "ema"
    with pytest.raises(ComponentError):
        spec.coerce("kama")
    with pytest.raises(ValidationError):
        ParamSpec(name="ma_type", kind="choice", default="x", coarse_values=("a", "b", "c", "d"))
    with pytest.raises(ValidationError):
        ParamSpec(
            name="ma_type",
            kind="choice",
            default="a",
            coarse_values=("a", "b", "c", "d"),
            fine_step=1,
        )


def test_F_0_4_1_param_spec_is_frozen() -> None:
    spec = int_param()
    with pytest.raises(ValidationError):
        spec.default = 20  # type: ignore[misc]


def test_F_0_4_1_at_most_64_cells_per_method() -> None:
    three = tuple(int_param(f"p{i}") for i in range(3))  # 4^3 = 64 cells
    four = tuple(int_param(f"p{i}") for i in range(4))  # 4^4 = 256 cells
    check_param_grid(three)
    with pytest.raises(ComponentError, match="256 coarse-grid cells exceed the maximum of 64"):
        check_param_grid(four)
    reg = ComponentRegistry()
    reg.register(make_entry("dummy_ok", three))
    with pytest.raises(ComponentError, match="exceed"):
        reg.register(make_entry("dummy_too_big", four))
    with pytest.raises(ComponentError, match="duplicate parameter names"):
        reg.register(make_entry("dummy_dup", (int_param("x"), int_param("x"))))


def test_F_0_4_1_resolve_params() -> None:
    specs = (
        int_param(),
        ParamSpec(
            name="threshold",
            kind="float",
            default=0.2,
            min=0.0,
            max=1.0,
            coarse_values=(0.1, 0.2, 0.3, 0.4),
            fine_step=0.05,
        ),
    )
    assert resolve_params(specs, None) == {"length": 10, "threshold": 0.2}
    assert resolve_params(specs, {"length": 12.0}) == {"length": 12, "threshold": 0.2}
    with pytest.raises(ComponentError, match="unknown parameters"):
        resolve_params(specs, {"lenght": 3})
    with pytest.raises(ComponentError, match="outside"):
        resolve_params(specs, {"threshold": 2.0})
    with pytest.raises(ComponentError, match="integer"):
        resolve_params(specs, {"length": 2.5})
    with pytest.raises(ComponentError, match="number"):
        resolve_params(specs, {"length": "10"})


# ----------------------------------------------------------------------------- extension


def stage_like_scan(reg: ComponentRegistry, edge_type: str, b: Bars) -> dict[str, int]:
    """Stand-in for stage code: it knows nothing about individual methods."""
    edges = load_edge_types()
    out = {}
    for cls in reg.list_by_edge_type(edge_type, edges):
        long_, short = cls.signals(b)
        out[cls.name] = int(long_.sum() + short.sum())
    return out


def test_F_0_4_1_adding_a_component_needs_only_registration() -> None:
    reg = ComponentRegistry()
    assert stage_like_scan(reg, "MR", bars()) == {}

    @reg.register
    class CloseAboveOpen(EntryComponent):
        """Dummy method: bullish bar."""

        name = "dummy_close_above_open"
        edge_type = "MR"
        params = (int_param(),)

        @classmethod
        def long_signals(cls, b: Bars, p: Mapping[str, ParamValue]) -> BoolArray:
            return b.close > b.open

    result = stage_like_scan(reg, "MR", bars())
    assert list(result) == ["dummy_close_above_open"]
    assert reg.get("dummy_close_above_open") is CloseAboveOpen
    assert [c.name for c in reg.list_by_role("entry")] == ["dummy_close_above_open"]


def test_F_0_4_1_signals_shape_and_directions() -> None:
    b = bars()
    long_only = make_entry("dummy_long_only", directions=("long",))
    long_, short = long_only.signals(b)
    assert long_.dtype == np.bool_ and long_.shape == (len(b),)
    assert not short.any()
    for cls in default_registry().entries():
        long_, short = cls.signals(b)
        assert long_.dtype == np.bool_ and short.dtype == np.bool_
        assert long_.shape == short.shape == (len(b),)


def test_F_0_4_1_bars_validation() -> None:
    with pytest.raises(ValueError, match="same length"):
        Bars(np.ones(3), np.ones(3), np.ones(2), np.ones(3))
    with pytest.raises(ValueError, match="1-D"):
        Bars(np.ones((2, 2)), np.ones(2), np.ones(2), np.ones(2))
    b = Bars([1, 2], [3, 4], [0.5, 1], [2, 3])  # type: ignore[arg-type]
    assert b.close.dtype == np.float64 and len(b) == 2
    m = b.mirrored()
    np.testing.assert_array_equal(m.high, [-0.5, -1.0])
    np.testing.assert_array_equal(m.low, [-3.0, -4.0])


def test_F_0_4_1_exit_spec_structure() -> None:
    spec = ExitSpec(signal_exit=True, time_exit_bars=50)
    assert spec.sl_atr is None and spec.trail_atr is None
    with pytest.raises(ValidationError):
        ExitSpec(time_exit_bars=0)
    with pytest.raises(ValidationError):
        ExitSpec(sl_atr=-1.0)
    with pytest.raises(ValidationError):
        ExitSpec(disaster_atr=3.0)  # type: ignore[call-arg]  # engine constant, not an exit

    reg = ComponentRegistry()

    @reg.register
    class TimeExit(ExitComponent):
        name = "dummy_time_exit"
        params = (int_param("bars", (5, 10, 20, 40)),)

        @classmethod
        def exit_spec(cls, params: Mapping[str, ParamValue]) -> ExitSpec:
            return ExitSpec(time_exit_bars=int(params["bars"]))

    assert reg.list_by_role("exit") == [TimeExit]
    assert TimeExit.exit_spec(resolve_params(TimeExit.params, None)).time_exit_bars == 10
