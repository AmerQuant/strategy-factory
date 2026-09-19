"""F-0.2.1, F-0.2.3, F-0.2.4: cost profiles, commission, swap, from_data spread, stress."""

from __future__ import annotations

import datetime as dt
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fixtures.t05 import MemoryLedger, bars_from_close, fx_hours, fx_meta, random_close
from hypothesis import given, settings
from hypothesis import strategies as st
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.costs.arrays import (
    build_cost_arrays,
    commission_kernel,
    commission_params,
    hourly_spread_table,
    resolve_from_data,
    round_trip_cost,
)
from strategy_factory.costs.profile import (
    Assignments,
    CostProfile,
    CostsConfig,
    load_assignments,
    load_profiles,
    resolve_profile,
    validate_all,
)
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import SplitConfig
from strategy_factory.data.split import DataAccess, SplitManager
from strategy_factory.data.store import SnapshotStore

REPO_COSTS = Path(__file__).resolve().parents[2] / "configs" / "costs"
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
ONES7 = np.ones(7)


def us(t: dt.datetime) -> int:
    return (t - EPOCH) // dt.timedelta(microseconds=1)


def bars(ts: list[dt.datetime], open_: float = 100.0, **extra: Any) -> dict[str, np.ndarray]:
    n = len(ts)
    out = {
        "ts": np.array([us(t) for t in ts], dtype=np.int64),
        "open": np.full(n, open_),
        "close": np.full(n, open_),
    }
    out.update({k: np.asarray(v) for k, v in extra.items()})
    return out


def profile(**over: Any) -> CostProfile:
    base: dict[str, Any] = {
        "name": "t",
        "status": "placeholder",
        "spread": {"mode": "fixed", "fixed": {"value": 0.02}},
        "commission": {"model": "none"},
        "swap": {"model": "none"},
    }
    base.update(over)
    return CostProfile.model_validate(base)


# -- F-0.2.1 profiles -----------------------------------------------------------------------
def test_F_0_2_1_shipped_placeholder_profiles_match_the_task() -> None:
    p = load_profiles(REPO_COSTS)
    t06 = {
        "us_equity_default",
        "fx_default",
        "metal_default",
        "index_cfd_default",
        "energy_cfd_default",
    }
    assert t06 <= set(p)  # T06b adds the generated Moneta profiles
    assert all(p[n].status == "placeholder" for n in t06)
    eq = p["us_equity_default"].model_dump()
    assert eq["spread"] == {"mode": "fixed", "fixed": {"value": 2.0, "unit": "bps"}}
    assert eq["commission"] == {
        "model": "per_share",
        "per_share": 0.005,
        "min_per_order": 1.0,
        "max_per_order": None,
        "currency": "USD",
    }
    assert eq["swap"] == {"model": "none"}
    assert eq["slippage"] == {"fixed": {"value": 1.0, "unit": "bps"}, "atr_fraction": 0.0}
    fx = p["fx_default"].model_dump()
    assert fx["spread"] == {
        "mode": "from_data",
        "scale": 1.0,
        "fallback": {"value": 1.0, "unit": "pip"},
    }
    assert fx["commission"] == {
        "model": "per_lot",
        "lot_size": 100000.0,
        "per_lot_per_side": 3.5,
        "currency": "USD",
    }
    assert (fx["swap"]["long"], fx["swap"]["short"], fx["swap"]["triple_weekday"]) == (
        -0.03,
        -0.03,
        "WED",
    )
    assert (fx["swap"]["rollover_time_local"], fx["swap"]["rollover_tz"]) == (
        "17:00",
        "America/New_York",
    )
    assert fx["slippage"] == {"fixed": {"value": 0.2, "unit": "pip"}, "atr_fraction": 0.02}
    for name, triple, slip in (
        ("metal_default", "WED", 0.02),
        ("index_cfd_default", "FRI", 0.02),
        ("energy_cfd_default", "FRI", 0.03),
    ):
        d = p[name].model_dump()
        assert d["spread"]["mode"] == "from_data" and d["spread"]["scale"] == 1.0
        assert d["commission"] == {"model": "none", "currency": "USD"}
        assert (d["swap"]["long"], d["swap"]["short"]) == (-0.03, -0.03)
        assert d["swap"]["triple_weekday"] == triple
        assert d["slippage"]["atr_fraction"] == slip


def test_F_0_2_1_every_universe_symbol_is_assigned() -> None:
    assigned, missing = validate_all(CostsConfig(costs_dir=REPO_COSTS))
    assert missing == []
    # T06b (D-520): broker-mapped symbols use the generated Moneta profiles
    assert assigned["EURUSD"] == "moneta_EURUSD+" and assigned["XAUUSD"] == "moneta_XAUUSD+"
    profs, asg = load_profiles(REPO_COSTS), load_assignments(REPO_COSTS)
    assert resolve_profile("USDJPY", "fx", profs, asg).pip_size == 0.01
    assert resolve_profile("EURUSD", "fx", profs, asg).pip_size == 0.0001


def test_F_0_2_1_missing_assignment_is_an_error() -> None:
    profs = {"t": profile()}
    with pytest.raises(ConfigError, match=r"no cost profile assigned.*costs are mandatory"):
        resolve_profile("ABC", "futures", profs, Assignments(groups={"fx": "t"}))
    with pytest.raises(ConfigError, match="unknown cost profile"):
        resolve_profile("ABC", "fx", profs, Assignments(groups={"fx": "nope"}))


def test_F_0_2_1_validate_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_COSTS.parents[1])
    runner = CliRunner()
    ok = runner.invoke(app, ["costs", "validate"])
    assert ok.exit_code == 0, ok.output
    assert "6 placeholder" in ok.output  # the 5 T06 placeholders + the D-324 proxy
    broken = tmp_path / "costs"
    shutil.copytree(REPO_COSTS, broken)
    text = (broken / "assignments.yaml").read_text(encoding="utf-8")
    (broken / "assignments.yaml").write_text(
        text.replace("  us_equity: us_share_cfd_proxy\n", ""), encoding="utf-8"
    )
    bad = runner.invoke(app, ["costs", "validate", "--costs-dir", str(broken)])
    assert bad.exit_code == 1
    # US equities that are not at the broker lose their proxy profile: costs are mandatory
    n_proxy = sum(1 for p in validate_all(CostsConfig())[0].values() if p == "us_share_cfd_proxy")
    assert f"{n_proxy} universe symbol(s) without a cost profile" in bad.output


def test_F_0_2_1_pips_need_pip_size() -> None:
    with pytest.raises(ValueError, match="uses pips but defines no pip_size"):
        profile(slippage={"fixed": {"value": 0.2, "unit": "pip"}})


def test_F_0_2_1_placeholder_flag_reaches_the_arrays() -> None:
    b = bars([dt.datetime(2024, 1, 2, tzinfo=dt.UTC)])
    assert build_cost_arrays(b, profile(), timeframe="1D").placeholder is True
    verified = profile(status="verified")
    assert build_cost_arrays(b, verified, timeframe="1D").placeholder is False


# -- spread / slippage ---------------------------------------------------------------------
def test_F_0_2_1_fixed_bps_spread_and_slippage_use_the_open() -> None:
    p = load_profiles(REPO_COSTS)["us_equity_default"]
    b = bars([dt.datetime(2024, 1, 2, tzinfo=dt.UTC)], open_=250.0)
    a = build_cost_arrays(b, p, timeframe="1D")
    assert a.half_spread[0] == pytest.approx(250.0 * 2e-4 / 2)  # 2 bps full -> 1 bp half
    assert a.slippage_fixed[0] == pytest.approx(250.0 * 1e-4)
    assert a.slippage_atr_frac == 0.0


def test_F_0_2_1_from_data_hourly_medians_hand_computed() -> None:
    t0 = dt.datetime(2024, 1, 2, tzinfo=dt.UTC)
    ts = np.array([us(t0 + dt.timedelta(hours=h + 24 * d)) for d in range(3) for h in (0, 1)])
    spread = np.array([1.0, 10.0, 3.0, 20.0, 2.0, 30.0])  # hour 0: 1,3,2 ; hour 1: 10,20,30
    t = hourly_spread_table(ts, spread, 1.5, fallback=0.5)
    assert t.full_spread[0] == pytest.approx(2.0 * 1.5)
    assert t.full_spread[1] == pytest.approx(20.0 * 1.5)
    assert t.full_spread[5] == 0.5 and 5 in t.fallback_hours
    with pytest.raises(DataError, match="no spread data for UTC hour 2"):
        hourly_spread_table(ts, spread, 1.0, fallback=None)


def test_F_0_2_1_from_data_must_be_resolved_first() -> None:
    fx = load_profiles(REPO_COSTS)["fx_default"]
    b = bars([dt.datetime(2024, 1, 2, tzinfo=dt.UTC)])
    with pytest.raises(ConfigError, match="resolve the from_data spread"):
        build_cost_arrays(b, fx, timeframe="1H")
    t0 = dt.datetime(2024, 1, 2, tzinfo=dt.UTC)
    dev = bars([t0 + dt.timedelta(hours=h) for h in range(24)], spread=np.arange(24) * 1e-5)
    resolved, table = resolve_from_data(fx, dev)
    arr = build_cost_arrays(bars([t0 + dt.timedelta(hours=5)]), resolved, timeframe="1H")
    assert arr.half_spread[0] == pytest.approx(5e-5 / 2)
    assert table.fallback_hours == ()
    assert "development bars" in resolved.source_note


def test_F_0_2_1_from_data_uses_development_bars_only(tmp_path: Path) -> None:
    """Holdout spreads (x1000) never reach the table built through DataAccess."""
    ts = fx_hours(
        dt.datetime(2021, 1, 3, 22, tzinfo=dt.UTC), dt.datetime(2023, 12, 29, 21, tzinfo=dt.UTC)
    )
    n = len(ts)
    split_cfg = SplitConfig()
    spread = np.full(n, 2e-5)
    df = bars_from_close(ts, random_close(n), spread=spread)
    store, cat = SnapshotStore(tmp_path), Catalog(tmp_path)
    meta = cat.register(store.write_snapshot(df, fx_meta(snapshot_hash=None)))
    cat.set_reference("EURUSD", "1H", meta.snapshot_hash or "")
    mgr = SplitManager(MemoryLedger(), split_cfg, store, cat)
    split = DataAccess(mgr).split("EURUSD", "1H")
    # rewrite the snapshot with huge spreads in the holdout: a new snapshot, new reference
    hold = np.array([t >= split.holdout_start for t in ts])
    df2 = bars_from_close(ts, random_close(n), spread=np.where(hold, 2e-2, 2e-5))
    meta2 = cat.register(store.write_snapshot(df2, fx_meta(snapshot_hash=None)))
    cat.set_reference("EURUSD", "1H", meta2.snapshot_hash or "")
    dev = DataAccess(mgr).arrays("EURUSD", "1H")
    fx = load_profiles(REPO_COSTS)["fx_default"]
    _, table = resolve_from_data(fx, dev)
    assert np.allclose(table.full_spread, 2e-5)


# -- commission ----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("commission", "qty", "price", "expected"),
    [
        ({"model": "percent", "rate": 0.001}, 100, 50.0, 5.0),
        ({"model": "per_share", "per_share": 0.005, "min_per_order": 1.0}, 100, 50.0, 1.0),  # min
        ({"model": "per_share", "per_share": 0.005, "min_per_order": 1.0}, 1000, 50.0, 5.0),
        (
            {"model": "per_share", "per_share": 0.005, "min_per_order": 1.0, "max_per_order": 7.0},
            5000,
            50.0,
            7.0,
        ),  # max
        (
            {"model": "per_lot", "lot_size": 100000, "per_lot_per_side": 3.5},
            92_592.59,
            1.08,
            3.5 * 0.9259259,
        ),
        ({"model": "none"}, 100, 50.0, 0.0),
    ],
)
def test_F_0_2_1_commission_models(
    commission: dict[str, Any], qty: float, price: float, expected: float
) -> None:
    p = profile(commission=commission)
    arr = build_cost_arrays(bars([dt.datetime(2024, 1, 2, tzinfo=dt.UTC)]), p, timeframe="1D")
    assert arr.commission(qty, price, "entry") == pytest.approx(expected, rel=1e-6)
    assert arr.commission(-qty, price, "exit") == pytest.approx(expected, rel=1e-6)
    assert commission_kernel(*commission_params(p), qty, price) == pytest.approx(expected, rel=1e-6)


def test_F_0_2_1_commission_params_codes() -> None:
    assert (
        commission_params(profile(commission={"model": "per_share", "per_share": 0.01}))[3]
        == math.inf
    )
    assert commission_params(profile())[0] == 0


# -- F-0.2.3 swap --------------------------------------------------------------------------
def fx_swap_profile(**swap: Any) -> CostProfile:
    s = {
        "model": "annual_rate",
        "long": -0.0365,
        "short": 0.0365,
        "day_count": 365,
        "rollover_time_local": "17:00",
        "rollover_tz": "America/New_York",
        "triple_weekday": "WED",
    }
    s.update(swap)
    return profile(swap=s)


def test_F_0_2_3_rollover_mask_follows_new_york_dst() -> None:
    p = fx_swap_profile()
    winter = [dt.datetime(2024, 1, 9, h, tzinfo=dt.UTC) for h in range(24)]  # Tuesday
    summer = [dt.datetime(2024, 7, 9, h, tzinfo=dt.UTC) for h in range(24)]
    aw = build_cost_arrays(bars(winter), p, timeframe="1H")
    asum = build_cost_arrays(bars(summer), p, timeframe="1H")
    assert [h for h in range(24) if aw.rollover_mask[h]] == [22]  # 17:00 EST = 22:00 UTC
    assert [h for h in range(24) if asum.rollover_mask[h]] == [21]  # 17:00 EDT = 21:00 UTC
    # the DST switch day itself (Sunday 2024-03-10) has no rollover; Monday 03-11 at 21:00
    switch = [dt.datetime(2024, 3, 8, 22, tzinfo=dt.UTC) + dt.timedelta(hours=h) for h in range(80)]
    a = build_cost_arrays(bars(switch), p, timeframe="1H")
    hits = [switch[i] for i in np.flatnonzero(a.rollover_mask)]
    assert hits == [
        dt.datetime(2024, 3, 8, 22, tzinfo=dt.UTC),
        dt.datetime(2024, 3, 11, 21, tzinfo=dt.UTC),
    ]


def test_F_0_2_3_annual_rate_swap_hand_computed_with_triple_wednesday() -> None:
    p = fx_swap_profile()
    days = [dt.datetime(2024, 1, 8, tzinfo=dt.UTC) + dt.timedelta(days=d) for d in range(7)]
    a = build_cost_arrays(bars(days, open_=1.0), p, timeframe="1D")
    assert a.rollover_mask.tolist() == [True, True, True, True, True, False, False]
    assert a.triple_mask.tolist() == [False, False, True, False, False, False, False]
    assert a.swap_long_per_notional_day[0] == pytest.approx(-0.0001)
    # long Monday open -> Saturday open: rollovers Mon, Tue, Wed(x3), Thu, Fri = 7 days
    notional = 100_000.0
    cost = round_trip_cost(a, 0, 5, notional, +1, 1.0, 1.0, 0.0, 0.0, close=ONES7)
    assert cost["swap"] == pytest.approx(7 * 0.0001 * notional)  # a charge
    short = round_trip_cost(a, 0, 5, notional, -1, 1.0, 1.0, 0.0, 0.0, close=ONES7)
    assert short["swap"] == pytest.approx(-7 * 0.0001 * notional)  # a credit
    # entered Thursday, exited Friday open: only Thursday's rollover
    assert round_trip_cost(a, 3, 4, notional, +1, 1.0, 1.0, 0.0, 0.0, close=ONES7)[
        "swap"
    ] == pytest.approx(0.0001 * notional)


def test_F_0_2_3_points_per_day_swap() -> None:
    p = profile(
        swap={"model": "points_per_day", "long": -0.5, "short": 0.2, "triple_weekday": "FRI"}
    )
    days = [dt.datetime(2024, 1, 11, tzinfo=dt.UTC) + dt.timedelta(days=d) for d in range(2)]
    a = build_cost_arrays(bars(days, open_=50.0), p, timeframe="1D")  # Thu, Fri
    assert a.triple_mask.tolist() == [False, True]
    assert a.swap_long_per_notional_day[0] == pytest.approx(-0.5 / 50.0)
    qty = 200.0  # notional 10,000
    cost = round_trip_cost(a, 0, 2 - 1, qty, +1, 50.0, 50.0, 0.0, 0.0, close=np.full(2, 50.0))
    assert cost["swap"] == pytest.approx(0.5 * qty)  # 1 day x 0.5 points x 200 units


def test_F_0_2_3_no_swap_profile_has_empty_masks() -> None:
    a = build_cost_arrays(
        bars([dt.datetime(2024, 1, 9, 22, tzinfo=dt.UTC)]), profile(), timeframe="1H"
    )
    assert not a.rollover_mask.any() and a.swap_long_per_notional_day[0] == 0.0


# -- F-0.2.4 stress ------------------------------------------------------------------------
@pytest.mark.parametrize("m", [1.5, 2.0, 3.0])
def test_F_0_2_4_stress_scales_spread_and_slippage_only(m: float) -> None:
    p = fx_swap_profile().model_copy(
        update={
            "commission": profile(commission={"model": "percent", "rate": 0.001}).commission,
            "slippage": profile(slippage={"fixed": {"value": 0.01}, "atr_fraction": 0.1}).slippage,
        }
    )
    b = bars([dt.datetime(2024, 1, 9, 22, tzinfo=dt.UTC)])
    base = build_cost_arrays(b, p, timeframe="1H")
    s = build_cost_arrays(b, p, m, timeframe="1H")
    assert s.half_spread[0] == pytest.approx(m * base.half_spread[0])
    assert s.slippage_fixed[0] == pytest.approx(m * base.slippage_fixed[0])
    assert s.slippage_atr_frac == pytest.approx(m * base.slippage_atr_frac)
    assert s.commission(10, 100.0) == base.commission(10, 100.0)
    assert (s.swap_long_per_notional_day == base.swap_long_per_notional_day).all()
    assert (s.rollover_mask == base.rollover_mask).all()
    assert load_assignments(REPO_COSTS).stress_multipliers == (1.5, 2.0, 3.0)


# -- cost monotonicity (property) ----------------------------------------------------------
TRADES = [(0, 3, 150.0, 1), (4, 9, 80.0, -1), (10, 20, 300.0, 1), (21, 27, 50.0, -1)]
DAYS = [dt.datetime(2024, 1, 8, tzinfo=dt.UTC) + dt.timedelta(days=d) for d in range(28)]
BARS = bars(DAYS, open_=100.0)


def total_cost(p: CostProfile, stress: float = 1.0) -> float:
    a = build_cost_arrays(BARS, p, stress, timeframe="1D")
    return sum(
        round_trip_cost(a, e, x, q, d, 100.0, 100.0, 2.0, 2.0, close=BARS["close"])["total"]
        for e, x, q, d in TRADES
    )


def make(spread: float, slip: float, atr: float, rate: float, swap: float) -> CostProfile:
    return profile(
        spread={"mode": "fixed", "fixed": {"value": spread}},
        slippage={"fixed": {"value": slip}, "atr_fraction": atr},
        commission={"model": "percent", "rate": rate},
        swap={"model": "annual_rate", "long": -swap, "short": -swap, "triple_weekday": "WED"},
    )


pos = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


@settings(max_examples=200, deadline=None)
@given(base=st.tuples(pos, pos, pos, pos, pos), which=st.integers(0, 4), bump=st.floats(1e-6, 1.0))
def test_F_0_2_4_raising_any_cost_component_never_lowers_total_cost(
    base: tuple[float, ...], which: int, bump: float
) -> None:
    raised = list(base)
    raised[which] += bump
    assert total_cost(make(*raised)) >= total_cost(make(*base)) - 1e-9


@settings(max_examples=50, deadline=None)
@given(base=st.tuples(pos, pos, pos, pos, pos))
def test_F_0_2_4_stress_levels_monotone(base: tuple[float, ...]) -> None:
    p = make(*base)
    costs = [total_cost(p, m) for m in (1.0, 1.5, 2.0, 3.0)]
    assert costs == sorted(costs)


# -- CLI show ------------------------------------------------------------------------------
@pytest.mark.db
def test_F_0_2_1_show_cli_display_only_for_short_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry_engine: Any
) -> None:
    root = tmp_path / "store"
    monkeypatch.setenv("SFAC_DATA_ROOT", str(root))
    monkeypatch.chdir(REPO_COSTS.parents[1])
    import strategy_factory.registry.engine as eng

    monkeypatch.setattr(eng, "make_engine", lambda *a, **k: registry_engine)
    ts = fx_hours(
        dt.datetime(2024, 1, 7, 22, tzinfo=dt.UTC), dt.datetime(2024, 1, 26, 21, tzinfo=dt.UTC)
    )
    df = bars_from_close(ts, random_close(len(ts)), spread=np.full(len(ts), 3e-5))
    store, cat = SnapshotStore(root), Catalog(root)
    meta = cat.register(store.write_snapshot(df, fx_meta(snapshot_hash=None)))
    cat.set_reference("EURUSD", "1H", meta.snapshot_hash or "")
    res = CliRunner().invoke(app, ["costs", "show", "EURUSD"])
    assert res.exit_code == 0, res.output
    assert "moneta_EURUSD+  [verified]" in res.output and "DISPLAY ONLY" in res.output
    assert "0.30" in res.output  # unscaled: 3e-5 = 0.30 pips
    # broker_scaled (D-523): a constant shape scaled to the Moneta mean 2.61 points = 0.26 pips
    assert "0.26" in res.output and "bar-weighted mean after scaling: 2.61e-05" in res.output


def test_F_0_2_1_show_cli_fixed_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SFAC_DATA_ROOT", str(tmp_path / "store"))
    monkeypatch.chdir(REPO_COSTS.parents[1])
    res = CliRunner().invoke(app, ["costs", "show", "AAPL"])
    assert res.exit_code == 0, res.output
    assert "moneta_AAPL  [verified]" in res.output and "broker      : AAPL" in res.output
    proxy = CliRunner().invoke(app, ["costs", "show", "AABA"])  # not at the broker (D-324)
    assert proxy.exit_code == 0, proxy.output
    assert "us_share_cfd_proxy" in proxy.output and "PLACEHOLDER" in proxy.output
    assert "ASSUMED, D-314" in proxy.output
    unknown = CliRunner().invoke(app, ["costs", "show", "NOPE_XYZ"])
    assert unknown.exit_code == 1
