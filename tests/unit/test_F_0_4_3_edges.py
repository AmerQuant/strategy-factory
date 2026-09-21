"""F-0.4.3: edge-type tags come from the YAML registry; the short entry mirrors the long."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest
from fixtures.hypothesis_budget import examples
from hypothesis import given, settings
from hypothesis import strategies as st

from strategy_factory.components.base import (
    Bars,
    BoolArray,
    ComponentError,
    EntryComponent,
    ParamValue,
)
from strategy_factory.components.edges import DEFAULT_EDGE_TYPES, load_edge_types
from strategy_factory.components.registry import ComponentRegistry, default_registry
from strategy_factory.core.errors import ConfigError

PROBES = default_registry().entries()


# ----------------------------------------------------------------------------- tags


def test_F_0_4_3_edge_types_come_from_yaml() -> None:
    edges = load_edge_types()
    assert DEFAULT_EDGE_TYPES.as_posix() == "configs/edges/edge_types.yaml"
    assert edges.ids() == ("MR", "TF", "SEASONAL")
    assert edges.get("MR").group_ids() == ("oscillator", "band_channel", "sequence", "momentum")
    assert edges.get("TF").group_ids() == (
        "ma",
        "channel_breakout",
        "volatility_trailing",
        "ichimoku",
        "momentum",
    )
    default_registry().check_edge_tags(edges)


def test_F_0_4_3_every_probe_group_is_populated() -> None:
    edges = load_edge_types()
    for edge_id in ("MR", "TF"):
        groups = {c.group for c in default_registry().list_by_edge_type(edge_id, edges)}
        assert groups == set(edges.get(edge_id).group_ids())


def _registry_with(edge_type: str, group: str | None = None) -> ComponentRegistry:
    def long_signals(cls: type, b: Bars, p: Mapping[str, ParamValue]) -> BoolArray:
        return b.close > b.open

    body: dict[str, object] = {
        "name": "dummy_tagged",
        "edge_type": edge_type,
        "group": group,
        "trigger": "state",
        "long_signals": classmethod(long_signals),
    }
    reg = ComponentRegistry()
    reg.register(type("Dummy", (EntryComponent,), body))
    return reg


def test_F_0_4_3_tags_not_in_yaml_are_rejected(tmp_path: Path) -> None:
    edges = load_edge_types()
    with pytest.raises(ConfigError, match="unknown edge type 'PB'"):
        _registry_with("PB").check_edge_tags(edges)
    with pytest.raises(ConfigError, match="unknown edge type"):
        default_registry().list_by_edge_type("PB", edges)
    with pytest.raises(ComponentError, match="not a group of edge type MR"):
        _registry_with("MR", "ichimoku").check_edge_tags(edges)


def test_F_0_4_3_new_edge_type_is_config_only(tmp_path: Path) -> None:
    text = DEFAULT_EDGE_TYPES.read_text(encoding="utf-8")
    text += "  - id: PB\n    name_en: pullback in trend\n    groups:\n      - {id: PB-G1}\n"
    cfg = tmp_path / "edge_types.yaml"
    cfg.write_text(text, encoding="utf-8")
    edges = load_edge_types(cfg)
    assert "PB" in edges.ids()
    reg = _registry_with("PB", "PB-G1")
    reg.check_edge_tags(edges)
    assert [c.name for c in reg.list_by_edge_type("PB", edges)] == ["dummy_tagged"]


@pytest.mark.parametrize(
    ("yaml_text", "match"),
    [
        ("edge_types: []\n", "at least one"),
        ("edge_types:\n  - {id: MR}\n  - {id: MR}\n", "duplicate edge type"),
        ("edge_types:\n  - {id: MR, groups: [{id: a}, {id: a}]}\n", "duplicate group"),
        ("edge_types:\n  - {id: MR, colour: red}\n", "colour"),
    ],
)
def test_F_0_4_3_invalid_edge_registry(tmp_path: Path, yaml_text: str, match: str) -> None:
    cfg = tmp_path / "edge_types.yaml"
    cfg.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ConfigError, match=match):
        load_edge_types(cfg)
    with pytest.raises(ConfigError, match="cannot read"):
        load_edge_types(tmp_path / "missing.yaml")


# ----------------------------------------------------------------------------- mirror


def random_bars(seed: int, n: int, drift: float, vol: float) -> Bars:
    rng = np.random.default_rng(seed)
    c = 100.0 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    o = np.r_[c[0], c[:-1]] * np.exp(rng.normal(0.0, vol / 4, n))
    h = np.maximum(o, c) * (1.0 + np.abs(rng.normal(0.0, vol / 2, n)))
    lo = np.minimum(o, c) * (1.0 - np.abs(rng.normal(0.0, vol / 2, n)))
    return Bars(o, h, lo, c)


def reflect(b: Bars) -> Bars:
    """Mirror on a *positive* price scale: ``p -> K - p`` (high and low swap)."""
    k = 4.0 * float(b.high.max())
    return Bars(k - b.open, k - b.low, k - b.high, k - b.close)


@settings(max_examples=examples(25), deadline=None)  # deadline off: first call may JIT-compile
@given(
    seed=st.integers(0, 2**32 - 1),
    n=st.integers(60, 260),
    drift=st.floats(-0.002, 0.002),
    vol=st.floats(0.002, 0.03),
)
def test_F_0_4_3_short_is_long_on_mirrored_prices(
    seed: int, n: int, drift: float, vol: float
) -> None:
    b = random_bars(seed, n, drift, vol)
    mirrored = reflect(b)
    for probe in PROBES:
        long_, short = probe.signals(b)
        m_long, m_short = probe.signals(mirrored)
        np.testing.assert_array_equal(short, m_long, err_msg=f"{probe.name}: short vs mirror")
        np.testing.assert_array_equal(long_, m_short, err_msg=f"{probe.name}: long vs mirror")


def test_F_0_4_3_mirror_is_exact_under_negation() -> None:
    b = random_bars(7, 400, 0.0, 0.01)
    for probe in PROBES:
        assert probe.mirror
        _, short = probe.signals(b)
        m_long, _ = probe.signals(b.mirrored())
        np.testing.assert_array_equal(short, m_long, err_msg=probe.name)
        assert probe.signals(b)[0].any() or probe.signals(b)[1].any(), probe.name


def test_F_0_4_3_mirror_example_rsi() -> None:
    b = random_bars(3, 300, 0.0, 0.02)
    long_, short = default_registry().get("mr_rsi2_below_10").signals(b)
    from strategy_factory.components.indicators import rsi

    r = rsi(b.close, 2)
    np.testing.assert_array_equal(long_, r < 10)
    np.testing.assert_array_equal(short, r > 90)


# ----------------------------------------------------------------------------- mirror: false


def _unmirrored(doc: str | None, with_short: bool) -> type:
    def long_signals(cls: type, b: Bars, p: Mapping[str, ParamValue]) -> BoolArray:
        return b.close > b.open

    def short_signals(cls: type, b: Bars, p: Mapping[str, ParamValue]) -> BoolArray:
        return np.zeros(len(b), dtype=np.bool_)

    body: dict[str, object] = {
        "__doc__": doc,
        "name": "dummy_unmirrored",
        "edge_type": "SEASONAL",
        "mirror": False,
        "long_signals": classmethod(long_signals),
    }
    if with_short:
        body["short_signals"] = classmethod(short_signals)
    return type("Unmirrored", (EntryComponent,), body)


@pytest.mark.parametrize(
    "doc",
    [None, "Seasonal long bias.", "Seasonal.\n\nNot mirrored:   \n"],
)
def test_F_0_4_3_mirror_false_requires_a_reason(doc: str | None) -> None:
    with pytest.raises(ComponentError, match="written reason"):
        ComponentRegistry().register(_unmirrored(doc, with_short=True))


def test_F_0_4_3_mirror_false_requires_own_short_rule() -> None:
    doc = "Turn-of-month.\n\nNot mirrored: the edge is a long-only flow effect."
    with pytest.raises(ComponentError, match="own short_signals"):
        ComponentRegistry().register(_unmirrored(doc, with_short=False))
    reg = ComponentRegistry()
    cls = reg.register(_unmirrored(doc, with_short=True))
    b = random_bars(1, 50, 0.0, 0.01)
    long_, short = cls.signals(b)
    np.testing.assert_array_equal(long_, b.close > b.open)
    assert not short.any()
