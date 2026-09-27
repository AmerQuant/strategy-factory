"""F-0.8.2 / T10b: the run-level ``config_hash`` covers the engine settings and the costs.

``BacktestSpec.spec_hash`` (T08) covers the strategy spec only. CLAUDE.md rule 8 asks the run
to be reproducible, so the resolved pipeline config carries the engine section (D-343, D-344,
D-347), the intrabar mode (D-002), the data snapshots and the **cost inputs**: the content
hash of each symbol's resolved profile, the Moneta broker-spec SHA-256 (D-340), the FX
conversion config (D-307) and the conversion pairs' snapshot hashes (D-316).

``code_version`` (git commit + dirty flag) is **stored, not hashed**.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from fixtures.bars import make_meta
from fixtures.t05 import bars_from_close, random_close
from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.core.config import (
    EngineConfig,
    PipelineConfig,
    check_cost_inputs,
    config_hash,
    load_engine_config,
    load_pipeline_config,
    resolve_config,
    validate_config,
)
from strategy_factory.core.errors import ConfigError
from strategy_factory.core.universe import Universe, UniverseEntry, write_universe
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.store import SnapshotStore

REPO = Path(__file__).resolve().parents[2]
GATES = REPO / "configs" / "gates" / "default.yaml"
T0 = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)

SPREAD_BPS = 5.0
PROFILE: dict[str, Any] = {
    "name": "test_share",
    "status": "verified",
    "source_note": "unit test",
    "spread": {"mode": "fixed", "fixed": {"value": SPREAD_BPS, "unit": "bps"}},
    "commission": {"model": "none"},
    "swap": {"model": "none"},
    "slippage": {"fixed": {"value": 0.01, "unit": "price"}, "atr_fraction": 0.01},
    "quote_ccy": "USD",
}


# -- fixtures ------------------------------------------------------------------------------
def costs_dir(tmp: Path, spread_bps: float = SPREAD_BPS) -> Path:
    cdir = tmp / "costs"
    cdir.mkdir(parents=True, exist_ok=True)
    profile = json.loads(json.dumps(PROFILE))
    profile["spread"]["fixed"]["value"] = spread_bps
    (cdir / "test_share.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")
    (cdir / "assignments.yaml").write_text(
        yaml.safe_dump({"groups": {"us_equity": "test_share"}, "symbols": {}}), encoding="utf-8"
    )
    return cdir


def fx_config(tmp: Path, peg: float = 7.80) -> Path:
    path = tmp / "fx_conversion.yaml"
    path.write_text(
        yaml.safe_dump(
            {"pairs": {"EUR": {"pair": "EURUSD", "invert": False}}, "pegs": {"HKD": peg}}
        ),
        encoding="utf-8",
    )
    return path


def universe_file(tmp: Path) -> Path:
    u = Universe(
        symbols=(
            UniverseEntry(
                symbol="SPY",
                asset_class="us_equity",
                reference_source="alpaca",
                timeframes=("1D",),
                cost_profile="test_share",
                calendar="nyse",
                group="us_equity",
                broker_symbol="SPY",
            ),
        )
    )
    path = tmp / "universe.yaml"
    write_universe(u, path)
    return path


@pytest.fixture
def store_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "store"
    monkeypatch.setenv("SFAC_DATA_ROOT", str(root))
    store, cat = SnapshotStore(root), Catalog(root)
    ts = [T0 + dt.timedelta(days=i) for i in range(60)]
    meta = cat.register(
        store.write_snapshot(
            bars_from_close(ts, random_close(60)),
            make_meta(symbol="SPY", timeframe="1D", source="alpaca", asset_class="us_equity"),
        )
    )
    cat.set_reference("SPY", "1D", meta.snapshot_hash or "")
    return root


def pipeline(tmp: Path, **kw: Any) -> PipelineConfig:
    base: dict[str, Any] = {
        "universe": universe_file(tmp),
        "symbols": ["SPY"],
        "timeframes": ["1D"],
        "stages": ["s01_edge"],
        "gates": GATES,
    }
    base.update(kw)
    return PipelineConfig.model_validate(base)


def resolved(tmp: Path, root: Path, spread_bps: float = SPREAD_BPS, **kw: Any) -> PipelineConfig:
    return resolve_config(
        pipeline(tmp, **kw),
        root,
        costs_dir=costs_dir(tmp, spread_bps),
        fx_config_path=fx_config(tmp),
    )


# -- the engine section is part of the hash (D-343, D-344, D-347) ----------------------------
def test_F_0_8_2_engine_section_defaults_match_the_repo_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(REPO)
    assert load_engine_config() == EngineConfig()  # the YAML restates the model defaults
    assert pipeline(tmp_path).engine == EngineConfig()  # and a config without the section


def test_F_0_8_2_engine_yaml_and_model_defaults_cannot_drift() -> None:
    """Deviation 3: the defaults live in the model and are restated in the YAML.

    Two sources of the same numbers must not drift, so every key the YAML sets has to equal
    the model default, and the YAML has to set every field that has one (``parity_qty_step``
    has none and is commented out, D-347).
    """
    path = REPO / "configs" / "engine" / "default.yaml"
    from_yaml = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = EngineConfig()
    # the two fields with no meaningful default stay commented out in the YAML (D-347, D-366)
    no_default = {"parity_qty_step", "parity_tick_size"}
    assert set(from_yaml) == set(EngineConfig.model_fields) - no_default
    for key, value in from_yaml.items():
        assert value == getattr(defaults, key), f"{key}: YAML {value} != model default"
    assert defaults.parity_qty_step is None  # no default: a parity run must state it (D-347)
    assert defaults.parity_tick_size is None  # likewise the mintick (D-366)
    text = path.read_text(encoding="utf-8")
    for key in no_default:
        assert f"# {key}" in text, f"{key} must be documented in the YAML, commented out"
    assert defaults.entry_requires_flat_at_signal is False  # D-367: the research behaviour


@pytest.mark.parametrize(
    "change",
    [
        {"atr_length": 20},  # D-343
        {"disaster_stop_atr": 2.5},  # D-130
        {"initial_capital": 50_000.0},
        {"notional": 50_000.0},
        {"futures_contracts": 2.0},  # D-329
        {"parity_qty_step": 0.01},  # D-347
    ],
)
def test_F_0_8_2_engine_setting_changes_the_config_hash(
    tmp_path: Path, store_root: Path, change: dict[str, Any]
) -> None:
    base = resolved(tmp_path, store_root)
    other = base.model_copy(update={"engine": base.engine.model_copy(update=change)})
    assert config_hash(other) != config_hash(base)
    assert base.canonical()["engine"]["atr_length"] == 14


def test_F_0_8_2_intrabar_mode_changes_the_config_hash(tmp_path: Path, store_root: Path) -> None:
    base = resolved(tmp_path, store_root)
    parity = base.model_copy(
        update={
            "intrabar_mode": "tradingview",
            "engine": base.engine.model_copy(update={"parity_qty_step": 1.0}),
        }
    )
    assert config_hash(parity) != config_hash(base)


def test_F_0_8_2_config_hash_ignores_key_order(tmp_path: Path, store_root: Path) -> None:
    cfg = resolved(tmp_path, store_root)
    data = cfg.canonical()
    shuffled = dict(reversed(list(data.items())))
    assert config_hash(shuffled) == config_hash(data) == config_hash(cfg)


def test_F_0_8_2_parity_run_without_the_step_is_refused(tmp_path: Path) -> None:
    cfg = pipeline(tmp_path, intrabar_mode="tradingview")
    with pytest.raises(ConfigError, match="need parity_qty_step"):
        validate_config(cfg)
    ok = pipeline(
        tmp_path,
        intrabar_mode="tradingview",
        engine={"parity_qty_step": 1.0, "atr_length": 14},  # D-343, see the next test
    )
    validate_config(ok)


def test_F_0_8_2_parity_run_must_state_the_pine_atr_length(tmp_path: Path) -> None:
    """D-343: a parity run reproduces a Pine script, so it states that script's ATR length."""
    from strategy_factory.core.config import PARITY_ATR_LENGTH_REQUIRED

    implicit = pipeline(tmp_path, intrabar_mode="tradingview", engine={"parity_qty_step": 1.0})
    assert implicit.engine.atr_length == 14  # the research default is there...
    with pytest.raises(ConfigError, match=r"must set engine.atr_length explicitly"):
        validate_config(implicit)  # ... but it was not chosen for this run
    # stating it explicitly is enough, even when it equals the default
    for length in (14, 21):
        explicit = pipeline(
            tmp_path,
            intrabar_mode="tradingview",
            engine={"parity_qty_step": 1.0, "atr_length": length},
        )
        validate_config(explicit)
    assert PARITY_ATR_LENGTH_REQUIRED  # the message is shared, like the step message
    # a research run is unaffected
    validate_config(pipeline(tmp_path))


def test_F_0_8_2_run_cannot_start_without_resolved_cost_inputs(
    tmp_path: Path, store_root: Path
) -> None:
    """Costs are mandatory (CLAUDE.md rule 4): an unresolved run is refused at start."""
    from strategy_factory.core.config import require_resolved, start_run

    cfg = resolved(tmp_path, store_root)
    assert require_resolved(cfg) is cfg
    without = cfg.model_copy(update={"cost_inputs": None})
    with pytest.raises(ConfigError, match="unresolved cost_inputs"):
        require_resolved(without)
    assert cfg.cost_inputs is not None
    partial = cfg.model_copy(
        update={"cost_inputs": cfg.cost_inputs.model_copy(update={"profiles": {}})}
    )
    with pytest.raises(ConfigError, match="unresolved cost_inputs"):
        require_resolved(partial)

    class Writer:
        def start_run(self, *a: Any, **k: Any) -> None:
            raise AssertionError("must not be reached")

    with pytest.raises(ConfigError, match="unresolved cost_inputs"):
        start_run(without, Writer())


def test_F_0_8_2_parity_config_message_equals_the_engine_message(tmp_path: Path) -> None:
    """The config refuses a parity run with the same words as ``run_backtest`` (D-347)."""
    from strategy_factory.core.config import PARITY_STEP_REQUIRED

    with pytest.raises(ConfigError) as err:
        validate_config(pipeline(tmp_path, intrabar_mode="tradingview"))
    assert PARITY_STEP_REQUIRED in str(err.value)


# -- the cost inputs are part of the hash (a) ------------------------------------------------
def test_F_0_8_2_cost_inputs_are_resolved(tmp_path: Path, store_root: Path) -> None:
    cfg = resolved(tmp_path, store_root)
    assert cfg.cost_inputs is not None
    assert cfg.cost_inputs.profile_names == {"SPY": "test_share"}
    assert len(cfg.cost_inputs.profiles["SPY"]) == 64
    assert cfg.cost_inputs.moneta_spec_sha256 is None  # no Moneta profile in this costs dir
    assert cfg.cost_inputs.fx_conversion["pegs"] == {"HKD": 7.80}
    assert cfg.cost_inputs.conversion_snapshots == {}  # SPY is quoted in USD


def test_F_0_8_2_a_different_spread_changes_the_config_hash(
    tmp_path: Path, store_root: Path
) -> None:
    """Regenerating a profile with another spread must change the run hash."""
    base = resolved(tmp_path, store_root, spread_bps=5.0)
    wider = resolved(tmp_path, store_root, spread_bps=9.0)
    assert base.cost_inputs is not None and wider.cost_inputs is not None
    assert base.cost_inputs.profiles["SPY"] != wider.cost_inputs.profiles["SPY"]
    assert config_hash(base) != config_hash(wider)
    # everything else is unchanged
    assert base.data_snapshots == wider.data_snapshots
    assert base.model_copy(update={"cost_inputs": None}) == wider.model_copy(
        update={"cost_inputs": None}
    )


def test_F_0_8_2_changing_the_peg_or_the_broker_spec_changes_the_hash(
    tmp_path: Path, store_root: Path
) -> None:
    base = resolved(tmp_path, store_root)
    other_peg = resolve_config(
        pipeline(tmp_path),
        store_root,
        costs_dir=costs_dir(tmp_path),
        fx_config_path=fx_config(tmp_path, peg=7.90),
    )
    assert config_hash(other_peg) != config_hash(base)
    assert base.cost_inputs is not None
    with_spec = base.model_copy(
        update={"cost_inputs": base.cost_inputs.model_copy(update={"moneta_spec_sha256": "f" * 64})}
    )
    assert config_hash(with_spec) != config_hash(base)


def test_F_0_8_2_conversion_snapshot_hash_is_part_of_the_config(
    tmp_path: Path, store_root: Path
) -> None:
    """A non-USD symbol binds its conversion pair's snapshot to the run (D-316)."""
    cdir = costs_dir(tmp_path)
    profile = json.loads(json.dumps(PROFILE))
    profile["quote_ccy"] = "EUR"
    (cdir / "test_share.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")
    cfg = pipeline(tmp_path)
    fx = fx_config(tmp_path)
    with pytest.raises(ConfigError, match="conversion pair"):
        resolve_config(cfg, store_root, costs_dir=cdir, fx_config_path=fx)
    store, cat = SnapshotStore(store_root), Catalog(store_root)
    ts = [T0 + dt.timedelta(days=i) for i in range(60)]
    meta = cat.register(
        store.write_snapshot(
            bars_from_close(ts, random_close(60, seed=2)),
            make_meta(symbol="EURUSD", timeframe="1D", source="dukascopy", asset_class="fx"),
        )
    )
    cat.set_reference("EURUSD", "1D", meta.snapshot_hash or "")
    out = resolve_config(cfg, store_root, costs_dir=cdir, fx_config_path=fx)
    assert out.cost_inputs is not None
    ref = out.cost_inputs.conversion_snapshots["EURUSD"]["1D"]
    assert ref.snapshot_hash == meta.snapshot_hash
    changed = out.model_copy(
        update={
            "cost_inputs": out.cost_inputs.model_copy(
                update={
                    "conversion_snapshots": {
                        "EURUSD": {"1D": ref.model_copy(update={"snapshot_hash": "b" * 64})}
                    }
                }
            )
        }
    )
    assert config_hash(changed) != config_hash(out)


def test_F_0_8_2_conversion_snapshot_is_required_for_every_timeframe(
    tmp_path: Path, store_root: Path
) -> None:
    """D-316 reads the pair at the traded timeframe, so every timeframe needs its snapshot."""
    cdir = costs_dir(tmp_path)
    profile = json.loads(json.dumps(PROFILE))
    profile["quote_ccy"] = "EUR"
    (cdir / "test_share.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")
    universe = Universe(
        symbols=(
            UniverseEntry(
                symbol="SPY",
                asset_class="us_equity",
                reference_source="alpaca",
                timeframes=("1D", "1H"),
                cost_profile="test_share",
                calendar="nyse",
                group="us_equity",
                broker_symbol="SPY",
            ),
        )
    )
    upath = tmp_path / "universe_2tf.yaml"
    write_universe(universe, upath)
    store, cat = SnapshotStore(store_root), Catalog(store_root)

    def snapshot(symbol: str, timeframe: str, source: str, asset_class: str, seed: int) -> str:
        step = dt.timedelta(days=1) if timeframe == "1D" else dt.timedelta(hours=1)
        ts = [T0 + step * i for i in range(60)]
        meta = cat.register(
            store.write_snapshot(
                bars_from_close(ts, random_close(60, seed=seed)),
                make_meta(
                    symbol=symbol, timeframe=timeframe, source=source, asset_class=asset_class
                ),
            )
        )
        cat.set_reference(symbol, timeframe, meta.snapshot_hash or "")
        return meta.snapshot_hash or ""

    snapshot("SPY", "1H", "alpaca", "us_equity", 3)  # SPY 1D comes from the store_root fixture
    eur_1d = snapshot("EURUSD", "1D", "dukascopy", "fx", 4)
    cfg = PipelineConfig.model_validate(
        {
            "universe": upath,
            "symbols": ["SPY"],
            "timeframes": ["1D", "1H"],
            "stages": ["s01_edge"],
            "gates": GATES,
        }
    )
    fx = fx_config(tmp_path)
    # EURUSD 1H is missing: the run is refused, and the message names exactly that pair/timeframe
    with pytest.raises(ConfigError, match=r"conversion pair\(s\) the run needs .*EURUSD 1H"):
        resolve_config(cfg, store_root, costs_dir=cdir, fx_config_path=fx)
    eur_1h = snapshot("EURUSD", "1H", "dukascopy", "fx", 5)
    out = resolve_config(cfg, store_root, costs_dir=cdir, fx_config_path=fx)
    assert out.cost_inputs is not None
    conv = out.cost_inputs.conversion_snapshots["EURUSD"]
    assert {tf: ref.snapshot_hash for tf, ref in conv.items()} == {"1D": eur_1d, "1H": eur_1h}


def test_F_0_8_2_unknown_quote_currency_is_refused(tmp_path: Path, store_root: Path) -> None:
    cdir = costs_dir(tmp_path)
    profile = json.loads(json.dumps(PROFILE))
    profile["quote_ccy"] = "SEK"
    (cdir / "test_share.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")
    with pytest.raises(ConfigError, match="no conversion rule for quote currency SEK"):
        resolve_config(
            pipeline(tmp_path), store_root, costs_dir=cdir, fx_config_path=fx_config(tmp_path)
        )


# -- `sfac reproduce` fails loudly on a cost-hash mismatch (a) --------------------------------
def test_F_0_8_2_check_cost_inputs_detects_a_changed_profile(
    tmp_path: Path, store_root: Path
) -> None:
    stored = resolved(tmp_path, store_root, spread_bps=5.0).canonical()
    fx = fx_config(tmp_path)
    assert check_cost_inputs(stored, costs_dir=costs_dir(tmp_path, 5.0), fx_config_path=fx) == []
    problems = check_cost_inputs(stored, costs_dir=costs_dir(tmp_path, 9.0), fx_config_path=fx)
    assert len(problems) == 1
    assert problems[0].startswith("SPY: cost profile changed")
    assert "test_share" in problems[0]


def test_F_0_8_2_check_cost_inputs_detects_a_changed_fx_config(
    tmp_path: Path, store_root: Path
) -> None:
    stored = resolved(tmp_path, store_root).canonical()
    problems = check_cost_inputs(
        stored, costs_dir=costs_dir(tmp_path), fx_config_path=fx_config(tmp_path, peg=7.90)
    )
    assert problems == ["configs/data/fx_conversion.yaml changed (pairs or pegs, D-307)"]


def test_F_0_8_2_check_cost_inputs_detects_a_changed_conversion_pair(
    tmp_path: Path, store_root: Path
) -> None:
    """A run's conversion pairs are part of its costs (D-316)."""
    stored = resolved(tmp_path, store_root).canonical()
    cdir = costs_dir(tmp_path)
    profile = json.loads(json.dumps(PROFILE))
    profile["quote_ccy"] = "EUR"  # the same run would now need EURUSD
    (cdir / "test_share.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")
    problems = check_cost_inputs(stored, costs_dir=cdir, fx_config_path=fx_config(tmp_path))
    assert any("conversion pairs the run needs changed" in p for p in problems)
    assert any("EURUSD" in p for p in problems)


def test_F_0_8_2_moneta_spec_sha_is_recorded_when_a_moneta_profile_is_used(
    tmp_path: Path, store_root: Path
) -> None:
    """A Moneta-derived profile binds the run to the broker file's SHA-256 (D-340)."""
    cdir = costs_dir(tmp_path)
    moneta = cdir / "moneta"
    moneta.mkdir()
    (cdir / "test_share.yaml").unlink()
    (moneta / "moneta_profiles.yaml").write_text(
        yaml.safe_dump({"profiles": [PROFILE]}), encoding="utf-8"
    )
    (moneta / "moneta_spec.csv.meta.json").write_text(
        json.dumps({"source": "x.xlsx", "sha256": "a" * 64}), encoding="utf-8"
    )
    fx = fx_config(tmp_path)
    cfg = resolve_config(pipeline(tmp_path), store_root, costs_dir=cdir, fx_config_path=fx)
    assert cfg.cost_inputs is not None
    assert cfg.cost_inputs.moneta_spec_sha256 == "a" * 64
    assert check_cost_inputs(cfg.canonical(), costs_dir=cdir, fx_config_path=fx) == []
    (moneta / "moneta_spec.csv.meta.json").write_text(
        json.dumps({"source": "x.xlsx", "sha256": "b" * 64}), encoding="utf-8"
    )
    problems = check_cost_inputs(cfg.canonical(), costs_dir=cdir, fx_config_path=fx)
    assert problems == [
        "Moneta broker spec changed (D-340): run used aaaaaaaaaaaa, configs give bbbbbbbbbbbb"
    ]


def test_F_0_8_2_check_cost_inputs_reports_a_run_without_them(
    tmp_path: Path, store_root: Path
) -> None:
    stored = resolved(tmp_path, store_root).canonical()
    stored.pop("cost_inputs")
    assert check_cost_inputs(stored) == [
        "cost_inputs are not recorded in the run config (the run predates T10b)"
    ]


def test_F_0_8_2_check_cost_inputs_reports_an_unresolvable_profile(
    tmp_path: Path, store_root: Path
) -> None:
    stored = resolved(tmp_path, store_root).canonical()
    empty = tmp_path / "gone"
    empty.mkdir()
    (empty / "assignments.yaml").write_text(yaml.safe_dump({"groups": {}}), encoding="utf-8")
    problems = check_cost_inputs(stored, costs_dir=empty, fx_config_path=fx_config(tmp_path))
    assert len(problems) == 1 and "cannot be resolved today" in problems[0]


# -- CLI ---------------------------------------------------------------------------------------
def test_F_0_8_2_cli_resolve_prints_the_engine_and_cost_sections(
    tmp_path: Path, store_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(REPO)
    path = tmp_path / "p.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "universe": str(universe_file(tmp_path)),
                "symbols": ["SPY"],
                "timeframes": ["1D"],
                "stages": ["s01_edge"],
                "gates": str(GATES),
                "engine": {"atr_length": 21},
            }
        ),
        encoding="utf-8",
    )
    cfg = load_pipeline_config(path)
    assert cfg.engine.atr_length == 21
    runner = CliRunner()
    out = runner.invoke(app, ["config", "resolve", str(path)])
    assert out.exit_code == 0, out.output
    assert '"atr_length": 21' in out.output and "cost_inputs" in out.output


def test_F_0_8_2_repo_sample_configs_still_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    for name in ("sample_h1.yaml", "mvp_daily.yaml"):
        p = REPO / "configs" / "pipeline" / name
        cfg = load_pipeline_config(p)
        validate_config(cfg, p)
        assert cfg.engine == EngineConfig()  # no engine section -> the documented defaults


@pytest.mark.db
def test_F_0_8_2_reproduce_fails_loudly_when_a_cost_profile_changed(
    tmp_path: Path, store_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sfac reproduce` must not silently rebuild a run with other costs (CLAUDE.md rule 4)."""
    from fixtures.registry_db import require_database, schema_url
    from sqlalchemy import Engine, select

    from strategy_factory.registry import tables as T
    from strategy_factory.registry.migrations import upgrade
    from strategy_factory.registry.writer import RegistryWriter

    # the CLI resolves the cost configs from the working directory
    work = tmp_path / "work"
    (work / "configs" / "data").mkdir(parents=True)
    cdir = costs_dir(tmp_path)
    shutil.copytree(cdir, work / "configs" / "costs")
    shutil.copy(fx_config(tmp_path), work / "configs" / "data" / "fx_conversion.yaml")
    stored = resolved(tmp_path, store_root, spread_bps=5.0).canonical()

    schema = f"t_{uuid.uuid4().hex[:16]}"
    admin = require_database()  # skips (never fails) when no database is reachable
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = schema_url(schema).render_as_string(hide_password=False)
    engine: Engine = create_engine(url, hide_parameters=True)
    try:
        upgrade(engine)
        with RegistryWriter(engine) as writer:
            run_id = writer.start_run(stored, seed=42)
            writer.add_trials(
                [
                    {
                        "run_id": run_id,
                        "stage": "s02_screen",
                        "family_id": "fam",
                        "spec_hash": "f" * 64,
                        "params": {"n": 1},
                    }
                ]
            )
        with engine.connect() as conn:
            trial_id = conn.execute(select(T.trials.c.id)).scalar_one()
        monkeypatch.setenv("SFAC_DB_URL", url)
        monkeypatch.chdir(work)
        runner = CliRunner()
        ok = runner.invoke(app, ["reproduce", "--trial", str(trial_id)])
        assert ok.exit_code == 0, ok.output
        assert "cost inputs: OK" in ok.output
        assert "cost_profile  : SPY -> test_share" in ok.output

        # widen the spread: the same run is no longer reproducible
        profile = yaml.safe_load(
            (work / "configs" / "costs" / "test_share.yaml").read_text(encoding="utf-8")
        )
        profile["spread"]["fixed"]["value"] = 9.0
        (work / "configs" / "costs" / "test_share.yaml").write_text(
            yaml.safe_dump(profile), encoding="utf-8"
        )
        bad = runner.invoke(app, ["reproduce", "--trial", str(trial_id)])
        assert bad.exit_code == 1
        assert "cost inputs of this run cannot be reproduced" in bad.output
        assert "SPY: cost profile changed" in bad.output
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
