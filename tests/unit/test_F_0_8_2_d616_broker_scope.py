"""F-0.8.2 / D-603 / D-616: ``symbol_scope: broker`` expands at resolution to an explicit list,
and every broker symbol left out is recorded with its reason."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from strategy_factory.core.config import PipelineConfig, config_hash, expand_broker_scope
from strategy_factory.core.errors import ConfigError


def entry(symbol: str, tfs: list[str], broker: str | None, tradable: bool = True) -> dict:
    return {
        "symbol": symbol,
        "asset_class": "us_equity",
        "reference_source": "alpaca",
        "timeframes": tfs,
        "cost_profile": "p",
        "calendar": "nyse",
        "group": "us_equity",
        "tradable": tradable,
        "broker_symbol": broker,
    }


@dataclass
class Ref:
    source: str


class FakeCatalog:
    def __init__(self, refs: dict[tuple[str, str], str]) -> None:
        self.refs = refs

    def has_reference(self, symbol: str, tf: str) -> bool:
        return (symbol, tf) in self.refs

    def get_reference(self, symbol: str, tf: str) -> Ref:
        return Ref(self.refs[(symbol, tf)])


@pytest.fixture
def universe(tmp_path: Path) -> Path:
    path = tmp_path / "universe.yaml"
    data = {
        "symbols": [
            entry("AAA", ["1D", "1H"], "AAA"),
            entry("BBB", ["1D"], "BBB"),  # no 1H in the universe
            entry("CCC", ["1D", "1H"], None),  # not at the broker
            entry("DDD", ["1D", "1H"], "DDD"),  # 1H reference missing
            entry("EEE", ["1D", "1H"], "EEE"),  # 1H reference from another source
            entry("ZZZ", ["1D", "1H"], "ZZZ"),
        ]
    }
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


REFS = {
    ("AAA", "1D"): "alpaca",
    ("AAA", "1H"): "alpaca",
    ("BBB", "1D"): "alpaca",
    ("CCC", "1D"): "alpaca",
    ("CCC", "1H"): "alpaca",
    ("DDD", "1D"): "alpaca",
    ("EEE", "1D"): "alpaca",
    ("EEE", "1H"): "dukascopy",
    ("ZZZ", "1D"): "alpaca",
    ("ZZZ", "1H"): "alpaca",
}


def cfg(universe: Path, tfs: tuple[str, ...]) -> PipelineConfig:
    return PipelineConfig(
        universe=universe, symbol_scope="broker", timeframes=tfs, stages=("s01_edge",)
    )


def test_F_0_8_2_d616_broker_scope_expands_to_an_explicit_sorted_list(universe: Path) -> None:
    out = expand_broker_scope(cfg(universe, ("1H",)), FakeCatalog(REFS))
    assert out.symbols == ("AAA", "ZZZ")
    assert set(out.scope_excluded) == {"BBB", "DDD", "EEE"}  # CCC is not a broker symbol
    assert "not in the universe entry" in out.scope_excluded["BBB"]
    assert "no alpaca reference" in out.scope_excluded["DDD"]
    assert "no alpaca reference" in out.scope_excluded["EEE"]


def test_F_0_8_2_d616_each_timeframe_resolves_its_own_scope(universe: Path) -> None:
    daily = expand_broker_scope(cfg(universe, ("1D",)), FakeCatalog(REFS))
    assert daily.symbols == ("AAA", "BBB", "DDD", "EEE", "ZZZ")
    assert daily.scope_excluded == {}


def test_F_0_8_2_d616_the_expansion_is_in_the_config_hash(universe: Path) -> None:
    base = cfg(universe, ("1H",))
    a = expand_broker_scope(base, FakeCatalog(REFS))
    fewer = dict(REFS)
    del fewer[("ZZZ", "1H")]
    b = expand_broker_scope(base, FakeCatalog(fewer))
    assert config_hash(a) != config_hash(b)


def test_F_0_8_2_d616_a_listed_scope_or_an_expanded_one_is_unchanged(universe: Path) -> None:
    listed = PipelineConfig(universe=universe, symbols=("AAA",), timeframes=("1D",), stages=("x",))
    assert expand_broker_scope(listed, FakeCatalog(REFS)) is listed
    once = expand_broker_scope(cfg(universe, ("1H",)), FakeCatalog(REFS))
    assert expand_broker_scope(once, FakeCatalog({})) is once


def test_F_0_8_2_d616_scope_rules(universe: Path) -> None:
    with pytest.raises(ValueError, match="at least one symbol"):
        PipelineConfig(universe=universe, timeframes=("1D",), stages=("x",))
    with pytest.raises(ConfigError, match="no symbol"):
        expand_broker_scope(cfg(universe, ("1H",)), FakeCatalog({}))
    assert not cfg(universe, ("1D",)).is_resolved  # an unexpanded scope is never resolved
