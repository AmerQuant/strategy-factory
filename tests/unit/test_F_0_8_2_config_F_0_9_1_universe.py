"""F-0.8.2 pipeline config (resolution, hash) and F-0.9.1 universe registry."""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from fixtures.bars import make_bars, make_meta
from fixtures.t05 import fx_bars, fx_meta
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.core.config import (
    PipelineConfig,
    config_hash,
    load_pipeline_config,
    require_resolved,
    resolve_config,
    start_run,
    validate_config,
)
from strategy_factory.core.errors import ConfigError, DataError, RegistryError
from strategy_factory.core.universe import (
    Universe,
    UniverseEntry,
    generate_universe,
    load_universe,
    validate_universe,
    write_universe,
)
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.store import SnapshotStore

REPO = Path(__file__).resolve().parents[2]
COSTS = REPO / "configs" / "costs"
GATES = REPO / "configs" / "gates" / "default.yaml"
W0 = dt.datetime(2024, 1, 7, 22, tzinfo=dt.UTC)


def entry(symbol: str, **kw: Any) -> UniverseEntry:
    base: dict[str, Any] = {
        "symbol": symbol,
        "asset_class": "fx",
        "reference_source": "dukascopy",
        "timeframes": ("1H", "1D"),
        "cost_profile": f"moneta_{symbol}+",  # T06b: Moneta profile (D-520)
        "calendar": "24x5",
        "group": "fx",
        "broker_symbol": f"{symbol}+",  # D-524
    }
    base.update(kw)
    return UniverseEntry.model_validate(base)


def small_universe(tmp: Path) -> Path:
    u = Universe(
        symbols=(
            entry("EURUSD"),
            entry("GBPUSD"),
            entry(
                "SPY",
                asset_class="us_equity",
                reference_source="alpaca",
                timeframes=("1D",),
                cost_profile="us_share_cfd_proxy",  # not (yet) broker-mapped: D-324 proxy
                calendar="nyse",
                group="us_equity",
                broker_symbol=None,
            ),
            entry(
                "VIX",
                asset_class="aux",
                reference_source="yahoo",
                timeframes=("1D",),
                cost_profile=None,
                calendar="nyse",
                group="aux",
                tradable=False,
                broker_symbol=None,
            ),
        )
    )
    path = tmp / "universe.yaml"
    write_universe(u, path)
    return path


def pipeline(tmp: Path, **kw: Any) -> PipelineConfig:
    base: dict[str, Any] = {
        "universe": small_universe(tmp),
        "symbols": ["EURUSD"],
        "timeframes": ["1H"],
        "stages": ["s01_edge"],
        "gates": GATES,
    }
    base.update(kw)
    return PipelineConfig.model_validate(base)


@pytest.fixture
def store_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "store"
    monkeypatch.setenv("SFAC_DATA_ROOT", str(root))
    return root


# -- F-0.8.2 --------------------------------------------------------------------------------
def test_F_0_8_2_resolution_picks_catalog_references(tmp_path: Path, store_root: Path) -> None:
    store, cat = SnapshotStore(store_root), Catalog(store_root)
    old = cat.register(
        store.write_snapshot(fx_bars(W0, W0 + dt.timedelta(days=5)), fx_meta(snapshot_hash=None))
    )
    new = cat.register(
        store.write_snapshot(fx_bars(W0, W0 + dt.timedelta(days=9)), fx_meta(snapshot_hash=None))
    )
    cat.set_reference("EURUSD", "1H", new.snapshot_hash or "")
    cfg = pipeline(tmp_path)
    assert not cfg.is_resolved
    resolved = resolve_config(cfg, store_root)
    ref = resolved.data_snapshots["EURUSD"]["1H"]
    assert ref.snapshot_hash == new.snapshot_hash != old.snapshot_hash
    assert ref.source == "dukascopy" and resolved.is_resolved
    assert require_resolved(resolved) is resolved
    assert config_hash(resolved) != config_hash(cfg)


def test_F_0_8_2_unresolved_snapshot_is_refused(tmp_path: Path, store_root: Path) -> None:
    cfg = pipeline(tmp_path, symbols=["EURUSD", "GBPUSD"])
    Catalog(store_root).register(
        SnapshotStore(store_root).write_snapshot(
            fx_bars(W0, W0 + dt.timedelta(days=3)), fx_meta(snapshot_hash=None)
        )
    )
    with pytest.raises(
        ConfigError, match="no reference snapshot in the catalog for: EURUSD 1H, GBPUSD 1H"
    ):
        resolve_config(cfg, store_root)
    with pytest.raises(ConfigError, match="unresolved data_snapshots"):
        require_resolved(cfg)

    class Writer:
        def start_run(self, *a: Any, **k: Any) -> None:
            raise AssertionError("must not be reached")

    with pytest.raises(ConfigError, match="unresolved"):
        start_run(cfg, Writer())


def test_F_0_8_2_registry_writer_requires_snapshots() -> None:
    from strategy_factory.registry.writer import require_snapshots

    for bad in (
        {},
        {"data_snapshots": {}},
        {"data_snapshots": {"X": {"1D": {"source": "a"}}}},
        {"data_snapshots": {"X": {"1D": {"source": "a", "snapshot_hash": "zz"}}}},
    ):
        with pytest.raises(RegistryError, match="no resolved data_snapshots"):
            require_snapshots(bad)
    require_snapshots({"data_snapshots": {"X": {"1D": {"source": "a", "snapshot_hash": "b" * 64}}}})


def test_F_0_8_2_config_hash_stable_under_key_order(tmp_path: Path) -> None:
    uni = small_universe(tmp_path)
    a = {
        "universe": str(uni),
        "symbols": ["EURUSD"],
        "timeframes": ["1H"],
        "stages": ["s01_edge"],
        "gates": str(GATES),
        "seed": 7,
        "data_snapshots": {"EURUSD": {"1H": {"source": "dukascopy", "snapshot_hash": "c" * 64}}},
    }
    b = dict(reversed(list(a.items())))
    pa, pb = tmp_path / "a.yaml", tmp_path / "b.yaml"
    pa.write_text(yaml.safe_dump(a, sort_keys=False), encoding="utf-8")
    pb.write_text(yaml.safe_dump(b, sort_keys=False), encoding="utf-8")
    assert pa.read_text() != pb.read_text()
    ha, hb = config_hash(load_pipeline_config(pa)), config_hash(load_pipeline_config(pb))
    assert ha == hb
    assert config_hash(load_pipeline_config(pa).model_copy(update={"seed": 8})) != ha


def test_F_0_8_2_config_hash_equals_registry_hash(tmp_path: Path) -> None:
    from strategy_factory.registry.writer import config_hash as registry_hash

    cfg = pipeline(
        tmp_path, data_snapshots={"EURUSD": {"1H": {"source": "d", "snapshot_hash": "d" * 64}}}
    )
    assert config_hash(cfg) == registry_hash(cfg.canonical())


def test_F_0_8_2_validation_errors(tmp_path: Path) -> None:
    for kw, msg in (
        ({"symbols": ["NOPE"]}, "NOPE: not in the universe"),
        ({"symbols": ["VIX"], "timeframes": ["1D"]}, "VIX: not tradable"),
        ({"symbols": ["SPY"], "timeframes": ["1H"]}, "SPY: timeframes"),
        ({"stages": ["s99_x"]}, "stages without gates"),
    ):
        with pytest.raises(ConfigError, match=msg):
            validate_config(pipeline(tmp_path, **kw))
    with pytest.raises(ValueError):
        pipeline(tmp_path, symbols=["EURUSD", "EURUSD"])


def test_F_0_8_2_source_mismatch_and_critical_quality(tmp_path: Path, store_root: Path) -> None:
    store, cat = SnapshotStore(store_root), Catalog(store_root)
    m = cat.register(
        store.write_snapshot(
            fx_bars(W0, W0 + dt.timedelta(days=3)), fx_meta(snapshot_hash=None, source="other")
        )
    )
    cat.set_reference("EURUSD", "1H", m.snapshot_hash or "")
    with pytest.raises(ConfigError, match="reference snapshot from 'other'"):
        resolve_config(pipeline(tmp_path), store_root)
    m2 = cat.register(
        store.write_snapshot(fx_bars(W0, W0 + dt.timedelta(days=4)), fx_meta(snapshot_hash=None))
    )
    cat.set_reference("EURUSD", "1H", m2.snapshot_hash or "")
    cat.set_quality_status(m2.key(), "critical")
    with pytest.raises(DataError, match="critical quality check"):
        resolve_config(pipeline(tmp_path), store_root)


def test_F_0_8_2_cli_resolve_and_validate(
    tmp_path: Path, store_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, cat = SnapshotStore(store_root), Catalog(store_root)
    m = cat.register(
        store.write_snapshot(fx_bars(W0, W0 + dt.timedelta(days=3)), fx_meta(snapshot_hash=None))
    )
    cat.set_reference("EURUSD", "1H", m.snapshot_hash or "")
    uni = small_universe(tmp_path)
    cfg_file = tmp_path / "p.yaml"
    cfg_file.write_text(
        yaml.safe_dump(
            {
                "universe": str(uni),
                "symbols": ["EURUSD"],
                "timeframes": ["1H"],
                "stages": ["s01_edge"],
                "gates": str(GATES),
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    ok = runner.invoke(app, ["config", "validate", str(cfg_file)])
    assert ok.exit_code == 0, ok.output
    res = runner.invoke(app, ["config", "resolve", str(cfg_file)])
    assert res.exit_code == 0, res.output
    assert m.snapshot_hash in res.output and "config_hash:" in res.output


def test_F_0_8_2_repo_sample_configs_are_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    for name in ("sample_h1.yaml", "mvp_daily.yaml"):
        path = REPO / "configs" / "pipeline" / name
        validate_config(load_pipeline_config(path), path)


# -- F-0.9.1 --------------------------------------------------------------------------------
def test_F_0_9_1_generation_from_existing_universes(tmp_path: Path) -> None:
    d = tmp_path / "u"
    d.mkdir()
    (d / "us_equity_daily.csv").write_text(
        "symbol,source_of_listing\nSPY,x\nAAPL,x\n", encoding="utf-8"
    )
    (d / "us_equity_hourly.csv").write_text(
        "symbol,reason,first_member_date,last_member_date\nSPY,etf,,\nCCE,sp500_pit,,\n",
        encoding="utf-8",
    )
    shutil.copy(REPO / "configs" / "universe" / "dukascopy.csv", d / "dukascopy.csv")
    shutil.copy(REPO / "configs" / "universe" / "aux_yahoo.csv", d / "aux_yahoo.csv")
    u = generate_universe(d, COSTS)
    by = u.by_symbol()
    assert by["SPY"].timeframes == ("1D", "1H") and by["AAPL"].timeframes == ("1D",)
    assert by["CCE"].timeframes == ("1H",)
    assert by["SPY"].reference_source == "alpaca" and by["SPY"].calendar == "nyse"
    assert by["USDJPY"].cost_profile == "moneta_USDJPY+" and by["XAUUSD"].calendar == "24x5"
    assert by["USDJPY"].broker_symbol == "USDJPY+" and by["AAPL"].broker_symbol == "AAPL"
    assert by["SPY"].broker_symbol is None and by["SPY"].cost_profile == "us_share_cfd_proxy"
    assert by["XAUUSD"].asset_class == "metal" and by["DEUIDXEUR"].group == "index_cfd"
    aux = [e for e in u.symbols if e.asset_class == "aux"]
    assert len(aux) == 7 and not any(e.tradable for e in aux)
    assert all(e.cost_profile is None for e in aux)
    path = tmp_path / "universe.yaml"
    write_universe(u, path)
    assert load_universe(path) == u
    assert validate_universe(u, COSTS) == []


def test_F_0_9_1_repo_universe_is_valid_and_complete() -> None:
    u = load_universe(REPO / "configs" / "universe.yaml")
    assert validate_universe(u, COSTS) == []
    counts: dict[str, int] = {}
    for e in u.symbols:
        counts[e.asset_class] = counts.get(e.asset_class, 0) + 1
    assert counts == {
        "us_equity": 6713,
        "fx": 15,
        "metal": 2,
        "energy_cfd": 2,
        "index_cfd": 10,
        "aux": 7,
    }


def test_F_0_9_1_validation_errors(tmp_path: Path, store_root: Path) -> None:
    dup = Universe(symbols=(entry("EURUSD"), entry("EURUSD", reference_source="other")))
    assert any("listed 2 times" in p for p in validate_universe(dup, COSTS))
    wrong = Universe(symbols=(entry("EURUSD", cost_profile="metal_default"),))
    assert any("assignments give 'moneta_EURUSD+'" in p for p in validate_universe(wrong, COSTS))
    orphan = Universe(
        symbols=(
            entry("ABC", asset_class="futures", cost_profile="fx_default", broker_symbol=None),
        )
    )
    assert any("no cost profile assigned" in p for p in validate_universe(orphan, COSTS))
    with pytest.raises(ValueError, match="tradable symbols need a cost_profile"):
        entry("EURUSD", cost_profile=None)
    with pytest.raises(ValueError, match="unknown asset_class"):
        entry("EURUSD", asset_class="bonds")

    store, cat = SnapshotStore(store_root), Catalog(store_root)
    a = cat.register(
        store.write_snapshot(make_bars(5), make_meta(symbol="EURUSD", source="alpaca"))
    )
    cat.set_reference("EURUSD", "1D", a.snapshot_hash or "")
    b = cat.register(store.write_snapshot(make_bars(6), make_meta(symbol="ZZZ", source="alpaca")))
    cat.set_reference("ZZZ", "1D", b.snapshot_hash or "")
    probs = validate_universe(Universe(symbols=(entry("EURUSD"),)), COSTS, store_root)
    assert any("catalog reference from 'alpaca', universe declares 'dukascopy'" in p for p in probs)
    assert any("catalog asset_class 'us_equity', universe 'fx'" in p for p in probs)
    assert any("ZZZ 1D: reference snapshot for a symbol not in the universe" in p for p in probs)


def test_F_0_9_1_cli_list_and_validate(
    tmp_path: Path, store_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(REPO)
    uni = small_universe(tmp_path)
    runner = CliRunner()
    res = runner.invoke(app, ["universe", "list", "--universe", str(uni), "--asset-class", "fx"])
    assert res.exit_code == 0 and "EURUSD" in res.output and "SPY" not in res.output
    assert "2 symbol(s): fx 2" in res.output
    ok = runner.invoke(app, ["universe", "validate", "--universe", str(uni)])
    assert ok.exit_code == 0, ok.output
    assert "4 symbols (3 tradable)" in ok.output


def test_F_0_9_1_report_only_for_non_broker_symbols(tmp_path: Path, store_root: Path) -> None:
    """D-524: universe_filter broker (default) refuses non-broker symbols; all marks them."""
    u = Universe(
        symbols=(entry("EURUSD"), entry("GBPUSD", cost_profile="fx_default", broker_symbol=None))
    )
    path = tmp_path / "u.yaml"
    write_universe(u, path)
    store, cat = SnapshotStore(store_root), Catalog(store_root)
    for sym in ("EURUSD", "GBPUSD"):
        meta = fx_meta(symbol=sym, source_symbol=sym, snapshot_hash=None)
        m = cat.register(store.write_snapshot(fx_bars(W0, W0 + dt.timedelta(days=5)), meta))
        cat.set_reference(sym, "1H", m.snapshot_hash or "")
    cfg = pipeline(tmp_path, universe=path, symbols=["EURUSD", "GBPUSD"])
    with pytest.raises(ConfigError, match="GBPUSD: not tradable at the broker"):
        resolve_config(cfg, store_root)
    resolved = resolve_config(cfg.model_copy(update={"universe_filter": "all"}), store_root)
    assert resolved.report_only == ("GBPUSD",) and resolved.is_resolved
    assert resolved.canonical()["report_only"] == ["GBPUSD"]  # stored in the run config


def test_F_0_9_1_cli_list_broker_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    runner = CliRunner()
    broker = runner.invoke(app, ["universe", "list", "--broker", "--asset-class", "fx"])
    assert broker.exit_code == 0 and "EURUSD+" in broker.output
    assert "15 symbol(s): fx 15" in broker.output
    rest = runner.invoke(app, ["universe", "list", "--no-broker", "--asset-class", "us_equity"])
    assert rest.exit_code == 0 and "AABA" in rest.output and "moneta_" not in rest.output
