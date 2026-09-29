"""D-654, D-664, D-665, D-670 (F-X.5, F-X.6): the synthetic universes.

The "real" series are the committed TradingView parity charts (SPY 1D, XAUUSD 1H): real data that
CI has. The null must match their drift and volatility exactly, keep OHLC consistent and the
calendar, stay close on ATR, and be deterministic by seed; the planted edge must be present in
its own statistic at the strong end and absent on the null.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest

from strategy_factory.core.config import PipelineConfig, SourceRef, config_hash
from strategy_factory.core.errors import ConfigError
from strategy_factory.selftest.parity_refs import (
    fixture,
    fixture_dir,
    load_chart_data,
    load_manifest,
)
from strategy_factory.synthetic.access import SyntheticDataAccess, synthetic_series
from strategy_factory.synthetic.config import (
    NullConfig,
    PlantedConfig,
    cell_key,
    load_null_config,
    load_planted_config,
    parse_cell,
)
from strategy_factory.synthetic.null import fit, null_bars, session_slots
from strategy_factory.synthetic.planted import assign, own_statistic, plant

REPO = Path(__file__).resolve().parents[2]
CHARTS = {"1D": "BATS_SPY, 1D.csv", "1H": "OANDA_XAUUSD, 60.csv"}


def chart(timeframe: str) -> dict[str, Any]:
    ch = load_chart_data(fixture(CHARTS[timeframe]), load_manifest(fixture_dir()))
    n = ch.close.size
    return {
        "ts": np.asarray(ch.ts, dtype=np.int64) * 1_000_000,
        "open": np.asarray(ch.open, dtype=np.float64),
        "high": np.asarray(ch.high, dtype=np.float64),
        "low": np.asarray(ch.low, dtype=np.float64),
        "close": np.asarray(ch.close, dtype=np.float64),
        "volume": np.arange(n, dtype=np.float64),  # another column: must pass through unchanged
    }


def median_atr(b: dict[str, Any], n: int = 14) -> float:
    h, lo, c = b["high"], b["low"], b["close"]
    tr = np.maximum(h[1:] - lo[1:], np.maximum(abs(h[1:] - c[:-1]), abs(lo[1:] - c[:-1])))
    atr = np.convolve(tr, np.ones(n) / n, mode="valid")
    return float(np.median(atr / c[n:]))


@pytest.fixture(scope="module", params=["1D", "1H"])
def pair(request: pytest.FixtureRequest) -> tuple[str, dict[str, Any], dict[str, Any]]:
    tf = str(request.param)
    real = chart(tf)
    return tf, real, null_bars(real, tf, NullConfig(), seed=7)


# -- the null: D-654's requirement, measured as M1 -------------------------------------------
def test_F_X_5_d664_drift_and_volatility_are_the_real_ones_per_slot(pair: Any) -> None:
    tf, real, syn = pair
    slot = session_slots(real["ts"], NullConfig().cap(tf))
    a, b = fit(real, slot), fit(syn, slot)
    assert a.slots.keys() == b.slots.keys()
    for v, s in a.slots.items():
        t = b.slots[v]
        assert t.gap_mu == pytest.approx(s.gap_mu, abs=1e-12)
        assert t.gap_sd == pytest.approx(s.gap_sd, rel=1e-9)
        assert t.body_mu == pytest.approx(s.body_mu, abs=1e-12)
        assert t.body_sd == pytest.approx(s.body_sd, rel=1e-9)
    # exact drift: the same first and last close
    assert syn["close"][0] == pytest.approx(real["close"][0], rel=1e-12)
    assert syn["close"][-1] == pytest.approx(real["close"][-1], rel=1e-9)
    lr, ls = np.diff(np.log(real["close"])), np.diff(np.log(syn["close"]))
    assert ls.std() == pytest.approx(lr.std(), rel=0.03)  # gap-body correlation: near, not exact


def test_F_X_5_d664_ohlc_is_consistent_and_the_calendar_is_real(pair: Any) -> None:
    _, real, syn = pair
    assert (syn["high"] >= np.maximum(syn["open"], syn["close"]) * (1 - 1e-12)).all()
    assert (syn["low"] <= np.minimum(syn["open"], syn["close"]) * (1 + 1e-12)).all()
    assert (syn["low"] > 0).all()
    np.testing.assert_array_equal(syn["ts"], real["ts"])
    np.testing.assert_array_equal(syn["volume"], real["volume"])


def test_F_X_5_d664_atr_stays_close_to_the_real_one(pair: Any) -> None:
    """ATR is the unit of every probe, stop and magnitude (T15a plan §2: within 1-5 % on the
    measured daily series, 4-7 % on hourly ones)."""
    _, real, syn = pair
    assert median_atr(syn) == pytest.approx(median_atr(real), rel=0.10)


def test_F_X_5_d664_the_null_has_no_serial_edge() -> None:
    real = chart("1D")
    ac = []
    for seed in range(20):
        r = np.diff(np.log(null_bars(real, "1D", NullConfig(), seed)["close"]))
        ac.append(np.corrcoef(r[:-1], r[1:])[0, 1])
    assert abs(float(np.mean(ac))) < 0.01  # real SPY daily: clearly negative


def test_F_X_5_d664_deterministic_by_seed() -> None:
    real = chart("1D")
    a = null_bars(real, "1D", NullConfig(), 11)
    b = null_bars(real, "1D", NullConfig(), 11)
    c = null_bars(real, "1D", NullConfig(), 12)
    for col in ("open", "high", "low", "close"):
        np.testing.assert_array_equal(a[col], b[col])
    assert not np.array_equal(a["close"], c["close"])


def test_F_X_5_d664_gaussian_sensitivity_is_the_same_moments() -> None:
    real = chart("1D")
    syn = null_bars(real, "1D", NullConfig(innovations="gaussian", vol_path=False), 3)
    assert syn["close"][-1] == pytest.approx(real["close"][-1], rel=1e-9)


# -- the planted edge (D-665, M3) --------------------------------------------------------------
@pytest.mark.parametrize(
    ("cell", "low", "high"),
    [
        (("MR", "long", 3.0), 2.2, 3.8),
        (("MR", "short", 3.0), 2.2, 3.8),
        (("TF", "both", 0.5), 0.4, 0.6),
    ],
)
def test_F_X_6_d665_the_planted_effect_is_present_in_its_own_statistic(
    cell: tuple[str, str, float], low: float, high: float
) -> None:
    cfg = PlantedConfig()
    null = null_bars(chart("1D"), "1D", cfg.base, 5)
    planted, truth = plant(null, cell, cfg, "1D", 9)
    assert truth.events or truth.segments
    assert low < own_statistic(planted, truth, cfg) < high
    # the same positions on the null series carry no effect
    assert abs(own_statistic(null, truth, cfg)) < 0.5 * low


def test_F_X_6_d665_tf_segments_alternate_and_keep_the_drift() -> None:
    cfg = PlantedConfig()
    null = null_bars(chart("1D"), "1D", cfg.base, 5)
    planted, truth = plant(null, ("TF", "both", 0.5), cfg, "1D", 9)
    signs = [s for _, _, s in truth.segments]
    assert len(signs) >= 3 and all(a == -b for a, b in itertools.pairwise(signs))
    lr = np.diff(np.log(null["close"]))
    lp = np.diff(np.log(planted["close"]))
    assert abs(lp.mean() - lr.mean()) < 0.01 * lr.std()  # alternating signs: ~no net drift


def test_F_X_6_d665_a_null_cell_plants_nothing() -> None:
    cfg = PlantedConfig()
    null = null_bars(chart("1D"), "1D", cfg.base, 5)
    same, truth = plant(null, None, cfg, "1D", 9)
    np.testing.assert_array_equal(same["close"], null["close"])
    assert truth.cell == "null" and not truth.events and not truth.segments


def test_F_X_6_d665_assignment_is_equal_shares_deterministic_and_complete() -> None:
    cfg = PlantedConfig()
    symbols = [f"S{i:03d}" for i in range(486)]
    a = assign(symbols, cfg, 1)
    assert a == assign(list(reversed(symbols)), cfg, 1)
    assert set(a) == set(symbols)
    counts = pl.Series(list(a.values())).value_counts()
    null_n = list(a.values()).count("null")
    assert null_n == round(486 * cfg.null_share)
    per_cell = [list(a.values()).count(cell_key(c)) for c in cfg.cells()]
    assert max(per_cell) - min(per_cell) <= 1 and sum(per_cell) == 486 - null_n
    assert len(counts) == len(cfg.cells()) + 1
    assert all(parse_cell(k) is None or cell_key(parse_cell(k)) == k for k in a.values())


# -- configs and identity (D-670) ---------------------------------------------------------------
def test_F_X_5_d664_the_shipped_yaml_restates_the_defaults() -> None:
    assert load_null_config(REPO / "configs/synthetic/null.yaml") == NullConfig()
    assert load_planted_config(REPO / "configs/synthetic/planted.yaml") == PlantedConfig()


def test_F_X_5_d670_a_real_config_hashes_as_before_and_a_source_changes_it() -> None:
    cfg = PipelineConfig(symbols=("SPY",), timeframes=("1D",), stages=("s01_edge",))
    data = cfg.canonical()
    assert "source" not in data and cfg.source_id == "real"
    src = SourceRef(kind="null", seed=1, generator=NullConfig().model_dump(mode="json"))
    syn = cfg.model_copy(update={"source": src})
    assert config_hash(syn.canonical()) != config_hash(data)
    assert syn.source_id == src.id and src.id.startswith("null:") and len(src.id) == 17
    other = SourceRef(kind="null", seed=2, generator=src.generator)
    assert other.id != src.id


class _Splits:
    """Just enough of a SplitManager for DataAccess: the real bars as a DataFrame."""

    def __init__(self, bars: dict[str, Any]) -> None:
        cols = {k: v for k, v in bars.items() if k != "ts"}
        ts = pl.Series("ts", bars["ts"]).cast(pl.Datetime("us", "UTC"))
        self.df = pl.DataFrame(cols).insert_column(0, ts)

    def reference(self, symbol: str, timeframe: str) -> str:
        return f"{symbol}|{timeframe}"

    def development_bars(self, ref: str) -> pl.DataFrame:
        return self.df


def test_F_X_5_d654_synthetic_data_access_serves_the_series_and_nothing_else() -> None:
    real = chart("1D")
    src = SourceRef(kind="null", seed=3, generator=NullConfig().model_dump(mode="json"))
    da = SyntheticDataAccess(_Splits(real), src)  # type: ignore[arg-type]
    got = da.arrays("SPY", "1D")
    want, _ = synthetic_series(src, "SPY", "1D", real)
    np.testing.assert_allclose(got["close"], want["close"], rtol=0, atol=0)
    np.testing.assert_array_equal(da.real_arrays("SPY", "1D")["close"], real["close"])
    assert da.bars("SPY", "1D")["close"].to_numpy().tolist() == got["close"].tolist()
    with pytest.raises(ConfigError, match="auxiliary"):
        da.aux("VIX", "SPY", "1D")


def test_F_X_6_d665_a_planted_source_needs_its_assignment() -> None:
    real = chart("1D")
    cfg = PlantedConfig(assignment={"SPY": "MR|long|3"})
    src = SourceRef(kind="planted", seed=3, generator=cfg.model_dump(mode="json"))
    _, truth = synthetic_series(src, "SPY", "1D", real)
    assert truth.cell == "MR|long|3" and truth.events
    with pytest.raises(ConfigError, match="no assignment"):
        synthetic_series(src, "QQQ", "1D", real)
