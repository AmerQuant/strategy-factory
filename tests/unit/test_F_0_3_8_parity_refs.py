"""F-0.3.8 sections 1-3: the parity reference store, the parity config and the Pine cost arrays.

Decisions: D-348 (the references, used as exported), D-343/D-347 (the required parity inputs),
D-362 (costs from the Pine settings only), D-363 (compare over the trade list's range).
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import zoneinfo
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from strategy_factory.components.base import ExitSpec
from strategy_factory.components.registry import default_registry
from strategy_factory.core.config import EngineConfig
from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.core.parity_config import (
    PARITY_DIR,
    ParityConfig,
    PineSettings,
    load_parity_config,
)
from strategy_factory.costs.parity import PARITY_PROFILE, commission_params, parity_cost_arrays
from strategy_factory.selftest.parity_refs import (
    MANIFEST,
    ChartData,
    cross_check_properties,
    fixture,
    fixture_dir,
    load_chart_data,
    load_manifest,
    load_properties,
    load_strategy_report,
    load_trade_list,
    pine_settings_from_source,
    raw_dir,
    sha256_of,
    verify,
)
from strategy_factory.selftest.parity_run import PARITY_EXIT_RULES

REPO = Path(__file__).resolve().parents[2]
T0 = dt.datetime(2024, 1, 2, 14, 30, tzinfo=dt.UTC)  # a SPY daily stamp: 09:30 New York

PINE: dict[str, Any] = {
    "atr_length": 14,
    "initial_capital": 100_000.0,
    "qty_type": "cash_amount",
    "qty_value": 100_000.0,
    "commission_type": "none",
    "commission_value": 0.0,
    "slippage_ticks": 0,
    "tick_size": 0.01,
    "pyramiding": 0,
    "process_orders_on_close": False,
    "calc_on_every_tick": False,
    "bar_magnifier": False,
    "fill_assumptions": "next bar's open",
    "export_timezone": "Etc/UTC",
}
ENGINE: dict[str, Any] = {
    "initial_capital": 100_000.0,
    "notional": 100_000.0,
    "disaster_stop_atr": 3.0,
    "atr_length": 14,
    "futures_contracts": 1,
    "parity_qty_step": 1,
    "parity_tick_size": 0.01,
}


# -- fixtures --------------------------------------------------------------------------------
def write_chart(path: Path, n: int = 6, step_s: int = 86_400) -> Path:
    rows = []
    for i in range(n):
        base = 100.0 + i
        rows.append(
            {
                "time": int(T0.timestamp()) + i * step_s,
                "open": base,
                "high": base + 1.0,
                "low": base - 1.0,
                "close": base + 0.5,
            }
        )
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["time", "open", "high", "low", "close"])
        w.writeheader()
        w.writerows(rows)
    return path


def write_trades(path: Path) -> Path:
    rows = [
        ["1", "Entry long", "buy", "2024-01-03 14:30", "101", "10", "", ""],
        ["1", "Exit long", "sell", "2024-01-05 14:30", "104", "10", "30", "30"],
        ["2", "Entry short", "sellShort", "2024-01-08 14:30", "106", "10", "", ""],
        ["2", "Exit short", "cover", "2024-01-09 14:30", "105", "10", "10", "40"],
        ["3", "Entry long", "buy", "2024-01-10 14:30", "107", "10", "", ""],
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "Trade #",
                "Type",
                "Signal",
                "Date/Time",
                "Price USD",
                "Contracts",
                "Profit USD",
                "Cumulative profit USD",
            ]
        )
        w.writerows(rows)
    return path


def write_manifest(folder: Path) -> Path:
    files = {}
    for p in sorted(folder.glob("*.csv")):
        rows = sum(1 for _ in p.open(encoding="utf-8")) - 1
        files[p.name] = {"sha256": sha256_of(p), "size_bytes": p.stat().st_size, "rows": rows}
    path = folder / MANIFEST
    path.write_text(json.dumps({"files": files}, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def refs(tmp_path: Path) -> Path:
    write_chart(tmp_path / "CHART.csv")
    write_trades(tmp_path / "TRADES.csv")
    write_manifest(tmp_path)
    return tmp_path


# -- §1 the reference store ------------------------------------------------------------------
def test_F_0_3_8_chart_data_is_used_exactly_as_exported(refs: Path) -> None:
    """D-348: no Sunday merge, no resampling, no shift to 00:00 UTC."""
    chart = load_chart_data(refs / "CHART.csv")
    assert len(chart) == 6
    first, last = chart.range()
    assert first == T0 and first.hour == 14 and first.minute == 30  # the NY open, untouched
    assert last == T0 + dt.timedelta(days=5)
    np.testing.assert_array_equal(chart.ts_us, chart.ts * 1_000_000)
    bars = chart.bars()
    assert set(bars) == {"ts", "open", "high", "low", "close"}
    assert bars["open"][0] == 100.0 and bars["close"][-1] == 105.5
    assert chart.index_of(T0 + dt.timedelta(days=2)) == 2
    with pytest.raises(DataError, match="not a bar start"):
        chart.index_of(T0 + dt.timedelta(hours=1))


def test_F_0_3_8_manifest_is_verified_on_every_load(refs: Path) -> None:
    chart = load_chart_data(refs / "CHART.csv")
    assert chart.sha256 == sha256_of(refs / "CHART.csv")
    entries = load_manifest(refs)
    assert set(entries) == {"CHART.csv", "TRADES.csv"}
    assert entries["CHART.csv"]["rows"] == 6
    # a single changed byte is caught
    path = refs / "CHART.csv"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("100.0", "100.1", 1), encoding="utf-8")
    with pytest.raises(DataError, match="does not match the manifest"):
        load_chart_data(path)


def test_F_0_3_8_missing_or_incomplete_manifest_is_an_error(refs: Path) -> None:
    (refs / MANIFEST).unlink()
    with pytest.raises(ConfigError, match="parity manifest not found"):
        load_chart_data(refs / "CHART.csv")
    (refs / MANIFEST).write_text(json.dumps({"files": {}}), encoding="utf-8")
    with pytest.raises(ConfigError, match="no 'files' mapping"):
        load_chart_data(refs / "CHART.csv")
    (refs / MANIFEST).write_text(
        json.dumps({"files": {"OTHER.csv": {"sha256": "x"}}}), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="not listed in"):
        verify(refs / "CHART.csv")


def test_F_0_3_8_malformed_chart_exports_are_refused(tmp_path: Path) -> None:
    bad = tmp_path / "CHART.csv"
    bad.write_text("time,open,high,low\n1,2,3,4\n", encoding="utf-8")
    write_manifest(tmp_path)
    with pytest.raises(DataError, match="missing column"):
        load_chart_data(bad)
    bad.write_text("time,open,high,low,close\n20,1,2,0.5,1\n10,1,2,0.5,1\n", encoding="utf-8")
    write_manifest(tmp_path)
    with pytest.raises(DataError, match="not strictly increasing"):
        load_chart_data(bad)
    bad.write_text("time,open,high,low,close\n10,1,0.5,2,1\n", encoding="utf-8")
    write_manifest(tmp_path)
    with pytest.raises(DataError, match="high < low"):
        load_chart_data(bad)


def test_F_0_3_8_trade_list_pairs_entries_with_exits(refs: Path) -> None:
    trades = load_trade_list(refs / "TRADES.csv")
    assert len(trades) == 5
    pairs = trades.trades()
    assert len(pairs) == 2  # trade 3 is still open
    assert trades.open_trades() == [3]
    entry, exit_ = pairs[0]
    assert entry.direction == 1 and entry.kind == "entry" and entry.price == 101.0
    assert exit_.when == dt.datetime(2024, 1, 5, 14, 30, tzinfo=dt.UTC)
    assert exit_.pnl == 30.0
    assert pairs[1][0].direction == -1  # the short
    assert trades.net_profit() == pytest.approx(40.0)
    covered = trades.covered_range()  # D-363: the comparison range
    assert covered[0] == dt.datetime(2024, 1, 3, 14, 30, tzinfo=dt.UTC)
    assert covered[1] == dt.datetime(2024, 1, 9, 14, 30, tzinfo=dt.UTC)


def test_F_0_3_8_trade_list_timezone_is_the_export_timezone(refs: Path) -> None:
    """D-348 records the chart's timezone; the rows are converted to UTC with it."""
    import zoneinfo

    ny = load_trade_list(refs / "TRADES.csv", zoneinfo.ZoneInfo("America/New_York"))
    utc = load_trade_list(refs / "TRADES.csv")
    assert ny.rows[0].when == dt.datetime(2024, 1, 3, 19, 30, tzinfo=dt.UTC)  # 14:30 NY
    assert utc.rows[0].when == dt.datetime(2024, 1, 3, 14, 30, tzinfo=dt.UTC)


def test_F_0_3_8_loading_never_writes_to_the_raw_store(refs: Path) -> None:
    before = {p.name: p.stat().st_mtime_ns for p in refs.iterdir()}
    load_chart_data(refs / "CHART.csv")
    load_trade_list(refs / "TRADES.csv")
    assert {p.name: p.stat().st_mtime_ns for p in refs.iterdir()} == before


# -- §2 the parity config --------------------------------------------------------------------
def config_dict(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "unit",
        "reference": {
            "chart_data": "CHART.csv",
            "symbol": "BATS:SPY",
            "timeframe": "1D",
        },
        "pine": dict(PINE),
        "engine": dict(ENGINE),
    }
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def test_F_0_3_8_parity_config_requires_every_pine_field() -> None:
    for field in PINE:
        incomplete = {k: v for k, v in PINE.items() if k != field}
        with pytest.raises(ValueError, match=field):
            ParityConfig.model_validate(config_dict(pine=None) | {"pine": incomplete})


def test_F_0_3_8_parity_config_requires_the_parity_inputs() -> None:
    """D-347 the quantity step, D-343 the Pine ATR length."""
    no_step = config_dict(engine={**ENGINE, "parity_qty_step": None})
    with pytest.raises(ValueError, match="parity_qty_step"):
        ParityConfig.model_validate(no_step)
    mismatch = config_dict(engine={**ENGINE, "atr_length": 20})
    with pytest.raises(ValueError, match="must equal the Pine"):
        ParityConfig.model_validate(mismatch)
    capital = config_dict(engine={**ENGINE, "initial_capital": 50_000.0})
    with pytest.raises(ValueError, match="initial_capital"):
        ParityConfig.model_validate(capital)
    ok = ParityConfig.model_validate(config_dict())
    assert ok.intrabar_mode == "tradingview"
    assert ok.min_matched_share == 0.98 and ok.max_net_profit_diff == 0.03  # D-011


def test_F_0_3_8_parity_config_refuses_unsupported_pine_settings() -> None:
    with pytest.raises(ValueError, match="pyramiding"):
        ParityConfig.model_validate(config_dict(pine={**PINE, "pyramiding": 2}))
    with pytest.raises(ValueError, match="unknown IANA time zone"):
        ParityConfig.model_validate(config_dict(pine={**PINE, "export_timezone": "Mars/Olympus"}))
    with pytest.raises(ValueError, match="positive value"):
        ParityConfig.model_validate(
            config_dict(pine={**PINE, "commission_type": "percent", "commission_value": 0.0})
        )


def test_F_0_3_8_parity_config_hash_covers_every_pine_value() -> None:
    base = ParityConfig.model_validate(config_dict())
    for field, value in (
        ("atr_length", 21),
        ("slippage_ticks", 2),
        ("commission_value", 1.0),
        ("process_orders_on_close", True),
        ("bar_magnifier", True),
        ("export_timezone", "America/New_York"),
    ):
        pine = {**PINE, field: value}
        if field == "atr_length":
            other = ParityConfig.model_validate(
                config_dict(pine=pine, engine={**ENGINE, "atr_length": value})
            )
        elif field == "commission_value":
            other = ParityConfig.model_validate(
                config_dict(pine={**pine, "commission_type": "percent"})
            )
        else:
            other = ParityConfig.model_validate(config_dict(pine=pine))
        assert other.content_hash() != base.content_hash(), field


def test_F_0_3_8_repo_parity_templates_are_valid(tmp_path: Path) -> None:
    files = sorted((REPO / PARITY_DIR).glob("*.yaml"))
    assert {p.name for p in files} == {
        "spy_mr_1d.yaml",
        "xauusd_tf_1h_long.yaml",
        "xauusd_tf_1h_short.yaml",
    }
    steps = {}
    mapped = set()
    for path in files:
        cfg = load_parity_config(path)
        assert cfg.engine.atr_length == cfg.pine.atr_length
        steps[cfg.reference.symbol] = cfg.engine.parity_qty_step
        if cfg.strategy is None:  # filled once the Pine sources arrive (D-361)
            continue
        mapped.add(cfg.name)
        # a mapped strategy names a registered entry component and a valid exit spec (T11 §3)
        default_registry().get(cfg.strategy.entry)
        ExitSpec.model_validate(cfg.strategy.exit)
        if cfg.strategy.exit_signal:  # D-370: and a known parity exit rule, if it uses one
            assert cfg.strategy.exit_signal in PARITY_EXIT_RULES
    # every live reference is mapped; the two-sided TF config is gone with its export (D-600)
    assert mapped == {"spy_mr_1d", "xauusd_tf_1h_long", "xauusd_tf_1h_short"}
    assert steps == {"BATS:SPY": 1.0, "OANDA:XAUUSD": 0.01}  # D-347
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"name": "x"}), encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid parity config"):
        load_parity_config(bad)
    with pytest.raises(ConfigError, match="not found"):
        load_parity_config(tmp_path / "missing.yaml")


# -- §3 costs from the Pine settings (D-362) -------------------------------------------------
def test_F_0_3_8_d362_commission_params_per_pine_type() -> None:
    def params(**over: Any) -> tuple[int, float, float, float]:
        return commission_params(PineSettings.model_validate({**PINE, **over}))

    assert params() == (0, 0.0, 0.0, 0.0)
    assert params(commission_type="percent", commission_value=0.075) == (1, 0.00075, 0.0, 0.0)
    per_contract = params(commission_type="per_contract", commission_value=0.005)
    assert per_contract[:2] == (2, 0.005) and per_contract[3] == np.inf  # no min, no max
    assert params(commission_type="per_order", commission_value=4.5) == (4, 4.5, 0.0, 0.0)


def test_F_0_3_8_d362_cost_arrays_have_no_spread_and_no_swap() -> None:
    pine = PineSettings.model_validate({**PINE, "slippage_ticks": 3, "tick_size": 0.01})
    costs = parity_cost_arrays(pine, 5)
    assert costs.profile_name == PARITY_PROFILE and not costs.placeholder
    np.testing.assert_array_equal(costs.half_spread, np.zeros(5))  # TradingView: no spread
    np.testing.assert_array_equal(costs.swap_long_per_notional_day, np.zeros(5))
    np.testing.assert_array_equal(costs.swap_short_per_notional_day, np.zeros(5))
    assert not costs.rollover_mask.any() and not costs.triple_mask.any()
    np.testing.assert_allclose(costs.slippage_fixed, np.full(5, 0.03))  # 3 ticks x 0.01
    assert costs.slippage_atr_frac == 0.0
    assert costs.stress == 1.0 and costs.quote_ccy == "USD"
    assert not costs.volume_step_assumed  # parity uses no broker step at all (D-347)
    with pytest.raises(ConfigError, match="at least one bar"):
        parity_cost_arrays(pine, 0)


def test_F_0_3_8_d362_costs_never_come_from_a_moneta_profile() -> None:
    """The parity arrays are built from `pine` alone: no profile is read."""
    import strategy_factory.costs.parity as parity_module

    source = Path(parity_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("resolve_profile", "load_profiles", "load_assignments", "moneta"):
        assert forbidden not in source, forbidden


def test_F_0_3_8_d362_commission_matches_the_kernel() -> None:
    """The parity commission params go through the same kernel as every other run."""
    from strategy_factory.engine.commission import commission_kernel

    pine = PineSettings.model_validate(
        {**PINE, "commission_type": "percent", "commission_value": 0.075}
    )
    code, p0, p1, p2 = commission_params(pine)
    assert commission_kernel(code, p0, p1, p2, 10.0, 200.0) == pytest.approx(0.00075 * 10 * 200)
    per_order = commission_params(
        PineSettings.model_validate(
            {**PINE, "commission_type": "per_order", "commission_value": 4.5}
        )
    )
    assert commission_kernel(*per_order, 10.0, 200.0) == pytest.approx(4.5)


def test_F_0_3_8_chart_data_feeds_run_backtest_unchanged(refs: Path) -> None:
    """The bars mapping is what `run_backtest` takes, with the exported stamps."""
    chart: ChartData = load_chart_data(refs / "CHART.csv")
    bars = chart.bars()
    assert bars["ts"].dtype == np.int64
    assert bars["ts"][0] == int(T0.timestamp()) * 1_000_000
    costs = parity_cost_arrays(PineSettings.model_validate(PINE), len(chart))
    assert costs.half_spread.shape == (len(chart),)


# -- section 6 scaffolding: the report and the D-011 verdict ---------------------------------
def test_F_0_3_8_d364_net_profit_difference_is_reported_both_ways() -> None:
    from strategy_factory.selftest.parity_report import NetProfitDiff

    diff = NetProfitDiff(
        engine=10_400.0, tradingview=10_000.0, initial_capital=100_000.0, small_share=0.01
    )
    assert diff.absolute == pytest.approx(400.0)
    assert diff.relative_to_tv == pytest.approx(0.04)
    assert diff.relative_to_capital == pytest.approx(0.004)
    assert not diff.tv_profit_is_small
    text = "\n".join(diff.lines())
    assert "relative to |TV|" in text and "relative to capital" in text and "FLAG" not in text


def test_F_0_3_8_d364_a_small_tv_profit_is_flagged_not_decided() -> None:
    from strategy_factory.selftest.parity_report import NetProfitDiff

    tiny = NetProfitDiff(
        engine=300.0, tradingview=100.0, initial_capital=100_000.0, small_share=0.01
    )
    assert tiny.tv_profit_is_small  # 100 is 0.1 % of capital
    assert tiny.relative_to_tv == pytest.approx(2.0)  # 200 % -- meaningless on its own
    assert tiny.relative_to_capital == pytest.approx(0.002)
    assert any("FLAG" in line for line in tiny.lines())
    zero = NetProfitDiff(engine=50.0, tradingview=0.0, initial_capital=100_000.0, small_share=0.01)
    assert zero.relative_to_tv is None and zero.tv_profit_is_small
    assert "n/a" in "\n".join(zero.lines())


def test_F_0_3_8_d011_verdict_uses_the_config_thresholds() -> None:
    from strategy_factory.selftest.parity_report import verdict

    cfg = ParityConfig.model_validate(config_dict())
    good = verdict(cfg, matched_share=0.99, engine_net=10_200.0, tv_net=10_000.0)
    assert good.trades_ok and good.profit_ok and good.passed
    few = verdict(cfg, matched_share=0.97, engine_net=10_200.0, tv_net=10_000.0)
    assert not few.trades_ok and not few.passed
    far = verdict(cfg, matched_share=0.99, engine_net=11_000.0, tv_net=10_000.0)
    assert far.trades_ok and not far.profit_ok  # 10 % > 3 %
    assert "FAIL" in "\n".join(far.lines())
    # D-364: a small TV profit is FLAGGED, not decided -- neither passed on the capital
    # figure (0.2 % here) nor failed on the relative one (200 %). The supervisor rules.
    tiny = verdict(cfg, matched_share=0.99, engine_net=300.0, tv_net=100.0)
    assert tiny.profit_state == "flagged"
    assert not tiny.profit_ok and not tiny.passed
    assert "the supervisor rules (D-364)" in "\n".join(tiny.lines())
    zero = verdict(cfg, matched_share=0.99, engine_net=50.0, tv_net=0.0)
    assert zero.profit_state == "flagged" and not zero.passed
    # the threshold is the config's (CLAUDE.md rule 1): a stricter one moves the flag
    strict = ParityConfig.model_validate(config_dict(small_net_profit_share=0.2))
    assert verdict(strict, 0.99, 10_200.0, 10_000.0).profit_state == "flagged"  # 10 % < 20 %
    assert verdict(cfg, 0.99, 10_200.0, 10_000.0).profit_state == "ok"
    looser = ParityConfig.model_validate(config_dict(min_matched_share=0.9))
    assert verdict(looser, 0.95, 10_200.0, 10_000.0).trades_ok


def test_F_0_3_8_reference_summary_names_the_missing_inputs() -> None:
    from strategy_factory.selftest.parity_report import reference_summary

    cfg = ParityConfig.model_validate(config_dict())
    text = "\n".join(reference_summary(cfg, 8467, "1993-01-29", "2026-09-18"))
    assert "BATS:SPY 1D" in text and "8,467" in text
    assert "NOT AVAILABLE YET (D-360)" in text  # no trade list
    assert "NOT MAPPED YET (D-361)" in text  # no strategy
    assert "atr_length 14" in text and "pine block only (D-362)" in text


# -- D-359: the repo fixtures, so the gate can run in CI -------------------------------------
MR_XLSX = "SF_parity_MR_-_RSI2_daily_BATS_SPY_2026-09-20.xlsx"
TF_XLSX = "SF_parity_TF_-_Donchian_1H_OANDA_XAUUSD_2026-09-20.xlsx"
MR_PINE = "SF parity MR - RSI2 daily.pine"
TF_PINE = "SF parity TF - Donchian 1H.pine"
# D-600: the one-sided TF references. The script's file name starts with two spaces -- that is
# the name in the raw store, which is read-only, so the fixture keeps it.
TF_LONG_XLSX = "SF_parity_TF_-_Donchian_1H_OANDA_XAUUSD_2026-09-20_Long.xlsx"
TF_SHORT_XLSX = "SF_parity_TF_-_Donchian_1H_OANDA_XAUUSD_2026-09-20_Short.xlsx"
TF_ONESIDE_PINE = "  SF parity TF - Donchian 1H oneside.pine"
#: Superseded by D-600: kept as fixtures for the loader tests, never read by a parity config.
SUPERSEDED = (TF_PINE, TF_XLSX)
NY = zoneinfo.ZoneInfo("America/New_York")
FIXTURES = (
    "BATS_SPY, 1D.csv",
    "OANDA_XAUUSD, 60.csv",
    MR_PINE,
    TF_PINE,
    TF_ONESIDE_PINE,
    MR_XLSX,
    TF_XLSX,
    TF_LONG_XLSX,
    TF_SHORT_XLSX,
)


def test_F_0_3_8_d359_every_reference_is_a_committed_fixture() -> None:
    """The gate reads these, so it never skips (CLAUDE.md rule 9)."""
    names = {p.name for p in fixture_dir().iterdir()}
    assert names == {*FIXTURES, MANIFEST}
    entries = load_manifest(fixture_dir())
    assert set(entries) == set(FIXTURES)
    total = sum(fixture(n).stat().st_size for n in FIXTURES)
    assert total < 4 * 1024 * 1024, f"{total / 1024 / 1024:.1f} MB is too much for the repo"


def test_F_0_3_8_d359_every_fixture_matches_its_own_manifest() -> None:
    """The fixture manifest is checked on every load, exactly like the raw one."""
    entries = load_manifest(fixture_dir())
    for name in FIXTURES:
        assert verify(fixture(name), entries) == entries[name]["sha256"]


def test_F_0_3_8_d359_fixtures_match_the_raw_store() -> None:
    """The raw store stays the source of truth (D-359); skipped only where it is absent."""
    raw = raw_dir()
    if raw is None:
        pytest.skip("SFAC_RAW_ROOT is not set (CI has no raw store)")
    if not (raw / MANIFEST).is_file():
        pytest.skip("the raw parity manifest is not written yet")
    raw_entries = load_manifest(raw)
    fixture_entries = load_manifest(fixture_dir())
    assert set(fixture_entries) <= set(raw_entries)
    for name, entry in fixture_entries.items():
        assert entry["sha256"] == raw_entries[name]["sha256"], name
        assert sha256_of(fixture(name)) == raw_entries[name]["sha256"], name


def test_F_0_3_8_d359_fixture_lookup_errors_are_clear() -> None:
    with pytest.raises(ConfigError, match="not found; have"):
        fixture("nope.csv")


# -- the real references, read from the fixtures ---------------------------------------------
@pytest.mark.parametrize(
    ("name", "rows", "first", "last"),
    [
        ("BATS_SPY, 1D.csv", 8467, "1993-01-29T14:30:00+00:00", "2026-09-18T13:30:00+00:00"),
        ("OANDA_XAUUSD, 60.csv", 21986, "2023-01-02T23:00:00+00:00", "2026-09-18T20:00:00+00:00"),
    ],
)
def test_F_0_3_8_fixture_chart_exports_load(name: str, rows: int, first: str, last: str) -> None:
    chart = load_chart_data(fixture(name), load_manifest(fixture_dir()))
    assert len(chart) == rows
    got_first, got_last = chart.range()
    assert got_first.isoformat() == first and got_last.isoformat() == last
    assert chart.high.min() >= chart.low.min()


@pytest.mark.parametrize(
    ("xlsx", "rows", "closed", "open_trades", "net", "reasons"),
    [
        (MR_XLSX, 924, 462, [], 185_810.06, {"PrevHigh": 365, "SL": 35, "Time": 62}),
        (TF_XLSX, 1745, 872, [873], -24_372.65, {"SL": 544, "TP": 273, "Time": 55}),
        (TF_LONG_XLSX, 1039, 519, [520], 20_637.96, {"SL": 309, "TP": 185, "Time": 25}),
        (TF_SHORT_XLSX, 800, 400, [], -43_610.28, {"SL": 260, "TP": 105, "Time": 35}),
    ],
)
def test_F_0_3_8_strategy_reports_load(
    xlsx: str, rows: int, closed: int, open_trades: list[int], net: float, reasons: dict[str, int]
) -> None:
    """The Trades sheet: exit-before-entry rows, an open trade dropped from the pairs."""
    from collections import Counter

    trades = load_strategy_report(fixture(xlsx), NY, load_manifest(fixture_dir()))
    assert len(trades) == rows
    pairs = trades.trades()
    assert len(pairs) == closed
    assert trades.open_trades() == open_trades
    assert trades.net_profit() == pytest.approx(net, abs=0.01)
    assert dict(Counter(x.signal for _, x in pairs)) == reasons
    assert all(e.kind == "entry" and x.kind == "exit" for e, x in pairs)
    assert all(e.when <= x.when for e, x in pairs)


def test_F_0_3_8_trade_times_are_in_the_chart_timezone() -> None:
    """America/New_York, verified against the chart export (D-348 records the timezone)."""
    mani = load_manifest(fixture_dir())
    trades = load_strategy_report(fixture(TF_XLSX), NY, mani)
    entry, _ = trades.trades()[0]
    assert entry.when == dt.datetime(2023, 1, 4, 8, 0, tzinfo=dt.UTC)  # 03:00 New York
    chart = load_chart_data(fixture("OANDA_XAUUSD, 60.csv"), mani)
    assert chart.open[chart.index_of(entry.when)] == pytest.approx(entry.price)
    # read as UTC instead, the same row lands on a bar whose open is a different price
    as_utc = load_strategy_report(fixture(TF_XLSX), dt.UTC, mani).trades()[0][0]
    assert chart.open[chart.index_of(as_utc.when)] != pytest.approx(entry.price)


def test_F_0_3_8_daily_trades_match_their_bar_by_date() -> None:
    """A daily trade row carries no time of day, so the bar is found by date."""
    mani = load_manifest(fixture_dir())
    trades = load_strategy_report(fixture(MR_XLSX), NY, mani)
    chart = load_chart_data(fixture("BATS_SPY, 1D.csv"), mani)
    entry, exit_ = trades.trades()[0]
    assert entry.when == dt.datetime(1993, 2, 19, 5, 0, tzinfo=dt.UTC)  # midnight New York
    with pytest.raises(DataError, match="not a bar start"):
        chart.index_of(entry.when)  # 05:00 UTC is not a bar; the bar is stamped 14:30 UTC
    i = chart.index_on_date(entry.when)
    assert chart.open[i] == pytest.approx(entry.price, abs=0.005)  # the export rounds to 2 dp
    j = chart.index_on_date(exit_.when)
    assert chart.open[j] == pytest.approx(exit_.price, abs=0.005)
    with pytest.raises(DataError, match="matches 0 bars"):
        chart.index_on_date(dt.datetime(1993, 2, 20, tzinfo=dt.UTC))  # a Saturday


# -- the Pine sources and the Properties cross-check ------------------------------------------
@pytest.mark.parametrize(
    ("pine_name", "xlsx", "tick"),
    [
        (MR_PINE, MR_XLSX, 0.01),
        (TF_PINE, TF_XLSX, 0.001),
        (TF_ONESIDE_PINE, TF_LONG_XLSX, 0.001),
        (TF_ONESIDE_PINE, TF_SHORT_XLSX, 0.001),
    ],
)
def test_F_0_3_8_pine_settings_agree_with_the_properties_sheet(
    pine_name: str, xlsx: str, tick: float
) -> None:
    """The strategy() call is the definition; the Properties sheet is what actually ran."""
    mani = load_manifest(fixture_dir())
    source = fixture(pine_name).read_text(encoding="utf-8-sig")
    settings = pine_settings_from_source(source, tick_size=tick, atr_length=14)
    assert settings["initial_capital"] == 100_000.0
    assert settings["qty_type"] == "cash_amount" and settings["qty_value"] == 100_000.0
    assert settings["commission_type"] == "percent" and settings["commission_value"] == 0.02
    assert settings["slippage_ticks"] == 0 and settings["pyramiding"] == 0
    assert settings["process_orders_on_close"] is False
    assert settings["calc_on_every_tick"] is False
    assert settings["bar_magnifier"] is False
    properties = load_properties(fixture(xlsx), mani)
    assert properties["Tick size"].startswith(str(tick)[:4])
    assert cross_check_properties(settings, properties) == []


def test_F_0_3_8_cross_check_reports_a_disagreement() -> None:
    mani = load_manifest(fixture_dir())
    properties = load_properties(fixture(MR_XLSX), mani)
    source = fixture(MR_PINE).read_text(encoding="utf-8-sig")
    settings = pine_settings_from_source(source, tick_size=0.01, atr_length=14)
    for field, value, expect in (
        ("commission_value", 0.05, "Commission"),
        ("initial_capital", 50_000.0, "Initial capital"),
        ("slippage_ticks", 2, "Slippage"),
        ("bar_magnifier", True, "Bar detalization"),
        ("calc_on_every_tick", True, "Script execution"),
    ):
        problems = cross_check_properties({**settings, field: value}, properties)
        assert len(problems) == 1 and problems[0].startswith(expect), (field, problems)
    assert cross_check_properties(settings, {}) == []  # no sheet: nothing to disagree with


def test_F_0_3_8_pine_parser_rejects_what_it_does_not_understand() -> None:
    with pytest.raises(DataError, match="no strategy"):
        pine_settings_from_source("// just a comment\n", 0.01, 14)
    with pytest.raises(DataError, match="unknown default_qty_type"):
        pine_settings_from_source('strategy("x", default_qty_type = strategy.made_up)\n', 0.01, 14)
    with pytest.raises(DataError, match="unknown commission_type"):
        pine_settings_from_source(
            'strategy("x", commission_type = strategy.commission.made_up)\n', 0.01, 14
        )


def test_F_0_3_8_the_repo_parity_configs_describe_the_real_references() -> None:
    """Each config's `pine` block must be exactly what its Pine source and report say."""
    mani = load_manifest(fixture_dir())
    for cfg_name, pine_name, xlsx in (
        ("spy_mr_1d.yaml", MR_PINE, MR_XLSX),
        ("xauusd_tf_1h_long.yaml", TF_ONESIDE_PINE, TF_LONG_XLSX),
        ("xauusd_tf_1h_short.yaml", TF_ONESIDE_PINE, TF_SHORT_XLSX),
    ):
        cfg = load_parity_config(REPO / PARITY_DIR / cfg_name)
        assert cfg.reference.trade_list == xlsx
        assert cfg.pine.export_timezone == "America/New_York"
        from_source = pine_settings_from_source(
            fixture(pine_name).read_text(encoding="utf-8-sig"),
            tick_size=cfg.pine.tick_size,
            atr_length=cfg.pine.atr_length,
        )
        recorded = cfg.pine.model_dump()
        for field, value in from_source.items():
            assert recorded[field] == value, f"{cfg_name}: {field}"
        assert cross_check_properties(recorded, load_properties(fixture(xlsx), mani)) == []


# -- D-366 / D-367: the two parity-only engine options ---------------------------------------
def test_F_0_3_8_d366_tick_rounding_applies_only_in_parity_mode() -> None:
    """The option reaches the engine in parity mode and never in research mode."""
    from strategy_factory.pipeline.backtest import parity_inputs

    cfg = EngineConfig(
        parity_qty_step=1.0, parity_tick_size=0.01, entry_requires_flat_at_signal=True
    )
    parity = parity_inputs(cfg, "tradingview")
    assert parity.tick_size == 0.01 and parity.entry_requires_flat is True
    research = parity_inputs(cfg, "pessimistic")
    assert research.tick_size is None and research.entry_requires_flat is False


def test_F_0_3_8_d366_engine_defaults_are_the_research_behaviour() -> None:
    cfg = EngineConfig()
    assert cfg.parity_tick_size is None
    assert cfg.entry_requires_flat_at_signal is False


def test_F_0_3_8_d366_ticks_round_half_away_from_zero() -> None:
    from strategy_factory.engine.kernel import _ticks

    assert _ticks(0.025, 0.01) == pytest.approx(0.03)  # half rounds up, not to even
    assert _ticks(0.035, 0.01) == pytest.approx(0.04)
    assert _ticks(0.0249, 0.01) == pytest.approx(0.02)
    assert _ticks(1.234, 0.0) == pytest.approx(1.234)  # no tick size: unchanged


def test_F_0_3_8_d366_parity_config_requires_the_mintick(tmp_path: Path) -> None:
    from strategy_factory.core.parity_config import ParityConfig

    base = config_dict()
    base["engine"] = {**ENGINE, "parity_tick_size": None}
    with pytest.raises(ValueError, match="parity_tick_size"):
        ParityConfig.model_validate(base)
    base["engine"] = {**ENGINE, "parity_tick_size": 0.05}
    with pytest.raises(ValueError, match="must equal the symbol's tick size"):
        ParityConfig.model_validate(base)
    base["engine"] = {**ENGINE, "parity_tick_size": 0.01}
    assert ParityConfig.model_validate(base).engine.parity_tick_size == 0.01


def test_F_0_3_8_d367_flat_gate_blocks_a_same_close_reentry() -> None:
    """The engine re-enters on the close that schedules an exit; the gate stops it (D-336)."""
    import numpy as np

    from strategy_factory.engine.api import (
        CostInputs,
        ExitParams,
        MarketArrays,
        ParityInputs,
        SizingInputs,
        simulate,
    )

    n = 12
    close = np.full(n, 100.0)
    market = MarketArrays(close.copy(), close + 1, close - 1, close.copy(), np.full(n, 1.0))
    entry = np.ones(n, dtype=np.bool_)  # a signal on every bar
    exit_sig = np.zeros(n, dtype=np.bool_)
    exit_sig[3] = True  # schedules an exit at the close of bar 3, filling at bar 4's open
    exit_sig[7] = True  # and a second one, so the re-entered trade closes and is visible
    zeros = np.zeros(n)
    costs = CostInputs(
        zeros.copy(), zeros.copy(), 0.0, zeros.copy(), zeros.copy(),
        np.zeros(n, dtype=np.bool_), np.zeros(n, dtype=np.bool_), (0, 0.0, 0.0, 0.0),
    )  # fmt: skip
    sizing = SizingInputs(mode=0, notional=1000.0, initial_capital=100_000.0)
    exits = ExitParams(disaster_atr=99.0)

    def run(flat_gate: bool) -> list[int]:
        r = simulate(
            market, entry, exit_sig, 1, exits, costs, sizing, 1,
            parity=ParityInputs(entry_requires_flat=flat_gate),
        )  # fmt: skip
        return r.entry_idx.tolist()

    default, gated = run(False), run(True)
    assert default[0] == gated[0] == 1  # the first entry is the same
    # D-336: the default re-enters at the very open where the exit filled (bar 4)
    assert default[1] == 4
    # D-367: the Pine gate refuses that re-entry, so the next entry is a bar later
    assert gated[1] == 5
    assert default != gated


# -- D-600: one-sided TF references ---------------------------------------------------------
def test_F_0_3_8_d600_each_one_sided_report_ran_the_direction_its_name_says() -> None:
    """The Properties sheet records the script's Direction input; a swapped export is caught
    here, by name, before the gate would fail on it for a less obvious reason."""
    mani = load_manifest(fixture_dir())
    for xlsx, side, cfg_name in (
        (TF_LONG_XLSX, "Long", "xauusd_tf_1h_long.yaml"),
        (TF_SHORT_XLSX, "Short", "xauusd_tf_1h_short.yaml"),
    ):
        assert load_properties(fixture(xlsx), mani)["Direction"] == side
        trades = load_strategy_report(fixture(xlsx), NY, mani).trades()
        expected = 1 if side == "Long" else -1
        assert {e.direction for e, _ in trades} == {expected}, xlsx
        cfg = load_parity_config(REPO / PARITY_DIR / cfg_name)
        assert cfg.strategy is not None and cfg.strategy.direction == side.lower()


def test_F_0_3_8_d600_superseded_references_are_never_read_by_a_config() -> None:
    """Kept for the loader tests, marked in the manifest, and unreachable from the gate."""
    entries = load_manifest(fixture_dir())
    for name in SUPERSEDED:
        assert "D-600" in entries[name].get("superseded", ""), name
    live = {n for n in FIXTURES if n not in SUPERSEDED}
    assert not any("superseded" in entries[n] for n in live)
    for path in sorted((REPO / PARITY_DIR).glob("*.yaml")):
        cfg = load_parity_config(path)
        used = {cfg.reference.chart_data, cfg.reference.trade_list}
        assert not used & set(SUPERSEDED), path.name


def test_F_0_3_8_d600_a_byte_identical_raw_copy_is_not_a_fixture() -> None:
    """`OANDA_XAUUSD, 60 2026-09-20b.csv` is the same bytes as `OANDA_XAUUSD, 60.csv`."""
    import json

    data = json.loads((fixture_dir() / MANIFEST).read_text(encoding="utf-8"))
    copies = data["duplicates_not_copied"]
    assert copies == {"OANDA_XAUUSD, 60 2026-09-20b.csv": "OANDA_XAUUSD, 60.csv"}
    for copy, original in copies.items():
        assert not (fixture_dir() / copy).exists()
        assert original in data["files"]
