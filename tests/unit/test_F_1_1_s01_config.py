"""F-1.1 / F-1.2 / D-233: the stage-1 config -- the battery is complete, the groups are real,
and an edge type with too few applicable groups is not run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from strategy_factory.components.registry import default_registry
from strategy_factory.core.errors import ConfigError
from strategy_factory.stages.config import DEFAULT_PATH, load_s01_config

REPO = Path(__file__).resolve().parents[2]


def repo_data() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((REPO / DEFAULT_PATH).read_text(encoding="utf-8"))
    return loaded


def written(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "s01_edge.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_F_1_1_the_repo_config_loads_and_lists_every_probe() -> None:
    cfg = load_s01_config(REPO / DEFAULT_PATH)
    registered = {c.name for c in default_registry().entries() if c.group}
    assert set(cfg.probes) == registered  # F-1.1 / F-1.2: all 17 probes run
    assert len(cfg.probes_of("MR")) == 9 and len(cfg.probes_of("TF")) == 8
    assert cfg.runnable_edge_types() == ("MR", "TF")
    assert cfg.edge_types["MR"].time_exit_bars == 5  # D-101
    assert cfg.edge_types["TF"].time_exit_bars == 50
    assert cfg.baseline.simulations == 1000  # D-102
    assert cfg.baseline.p_floor == pytest.approx(1 / 1001)  # D-606


def test_F_1_1_group_membership_is_in_config_and_matches_the_registry() -> None:
    cfg = load_s01_config(REPO / DEFAULT_PATH)
    assert set(cfg.edge_types["MR"].applicable_groups) == {
        "oscillator",
        "band_channel",
        "sequence",
        "momentum",
    }
    reg = default_registry()
    for probe in cfg.probes:
        comp = reg.get(probe)
        assert comp.group in cfg.edge_types[comp.edge_type].applicable_groups, probe


def test_F_1_1_a_missing_probe_is_refused(tmp_path: Path) -> None:
    data = repo_data()
    del data["probes"]["mr_rsi2_below_10"]
    with pytest.raises(ConfigError, match=r"mr_rsi2_below_10.*missing"):
        load_s01_config(written(tmp_path, data))


def test_F_1_1_an_unknown_probe_or_group_is_refused(tmp_path: Path) -> None:
    data = repo_data()
    data["probes"]["no_such_probe"] = {"warmup_bars": 1}
    with pytest.raises(ConfigError, match="no_such_probe"):
        load_s01_config(written(tmp_path, data))
    data = repo_data()
    data["edge_types"]["MR"]["applicable_groups"].append("astrology")
    with pytest.raises(ConfigError, match="astrology"):
        load_s01_config(written(tmp_path, data))


def test_F_1_1_d233_a_type_with_too_few_applicable_groups_is_not_run(tmp_path: Path) -> None:
    data = repo_data()
    data["edge_types"]["MR"]["applicable_groups"] = ["oscillator", "band_channel", "sequence"]
    cfg = load_s01_config(written(tmp_path, data))
    assert cfg.runnable_edge_types() == ("TF",)


def test_F_1_1_constants_are_validated(tmp_path: Path) -> None:
    for path, value in (
        (("baseline", "simulations"), 0),
        (("ess", "magnitude_target_atr"), -1),
        (("edge_types", "TF", "time_exit_bars"), 0),
    ):
        data = repo_data()
        node = data
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value
        with pytest.raises(ConfigError, match="invalid stage-1 config"):
            load_s01_config(written(tmp_path, data))
