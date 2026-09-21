"""T06b: Moneta broker file, generated profiles, D-312 swap, D-315 sizing, mapping, universe.

Features F-0.2.1, F-0.2.2, F-0.2.3, F-0.9.1; decisions D-312 ... D-315, D-317 ... D-325, D-340.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from fixtures.hypothesis_budget import examples
from hypothesis import given, settings
from hypothesis import strategies as st
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.costs.arrays import (
    build_cost_arrays,
    commission_kernel,
    commission_params,
    cost_breakdown_shares,
    resolve_from_data,
    round_trip_cost,
    size_lots,
)
from strategy_factory.costs.moneta import (
    SPEC_CSV,
    SPEC_META,
    MappingConfig,
    build,
    import_spec,
    load_moneta_config,
    map_symbols,
    name_score,
    normalize_row,
    profile_dict,
    proxy_profile_dict,
    read_spec_csv,
)
from strategy_factory.costs.profile import CostProfile, CostsConfig, load_profiles, validate_all

REPO = Path(__file__).resolve().parents[2]
REPO_COSTS = REPO / "configs" / "costs"
MONETA_DIR = REPO_COSTS / "moneta"
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
SHA = "f" * 64
HEADER = [
    "Symbol",
    "Description",
    "Point value",
    "Digits",
    "Contract Size",
    "Profit cal Mode",
    "Leverage",
    "Min volume per click",
    "Max volume per click",
    "Volume Step",
    "Margin Call",
    "Stop-out Margin",
    "Spread(For reference only)",
    "Commission",
    "3-day swap",
    "SWAP long",
    "SWAP short",
    "Swap Type",
    "Quote sample",
    "Trading time",
]
TT = "\nMonday: 00:01-23:58\nTuesday: 00:01-23:58\n"


def cells(
    symbol: str,
    desc: str,
    pv: str,
    digits: int,
    cs: str,
    step: float,
    spread: Any,
    comm: Any,
    triple: Any,
    sl: Any,
    ss: Any,
    stype: Any,
    quote: Any,
    region: str | None = None,
) -> dict[str, Any]:
    vals = [
        symbol,
        desc,
        pv,
        digits,
        cs,
        "CFD",
        100,
        step,
        100,
        step,
        80,
        50,
        spread,
        comm,
        triple,
        sl,
        ss,
        stype,
        quote,
        TT,
    ]
    d = dict(zip(HEADER, vals, strict=True))
    if region is not None:
        d["Region"] = region
    return d


EURUSD = cells(
    "EURUSD+",
    "Euro vs US Dollar",
    "1.0 USD",
    5,
    "100000 EUR",
    0.01,
    2.61,
    "6.0 USD per lot",
    "Wednesday",
    -9.46,
    4.69,
    "in points",
    "1.08",
)
USDTRY = cells(
    "USDTRY+",
    "US Dollar vs Lira",
    "1.0 TRY",
    5,
    "100000 USD",
    0.01,
    2169.55,
    "6.0 USD per lot",
    "Thursday",
    -4466.5,
    1112.98,
    "in points",
    "38.1",
)
CLOIL = cells(
    "CL-OIL",
    "Crude Oil Future CFD",
    "1.0 USD",
    3,
    "1000 barrels",
    0.01,
    30.43,
    "-",
    "-",
    "-",
    "-",
    "-",
    "68.310",
)
SP500 = cells(
    "SP500.r",
    "S&P 500 Cash",
    "0.01 USD",
    2,
    "1 USD",
    0.01,
    36.08,
    "-",
    "Friday",
    -1.5024,
    0.27989,
    "in currency",
    "6000.1",
)
GER40 = cells(
    "GER40.r",
    "DAX Cash",
    "0.01 EUR",
    2,
    "1 EUR",
    0.01,
    84.6,
    "-",
    "Friday",
    -3.4908,
    0.1106,
    "in currency",
    "24000.5",
)
AAPL = cells(
    "AAPL",
    "Apple Inc.",
    "0.01 USD",
    2,
    "1 Share",
    0.1,
    9.24,
    "-",
    "Friday",
    -6.88,
    -3.5,
    "in percentage terms",
    211.06,
    region="Stock US",
)
AALG = cells(
    "AALG",
    "AMERICAN AIRLINES GROUP INC",
    "0.01 USD",
    2,
    "1 Share",
    0.1,
    7.12,
    "-",
    "Friday",
    -6.88,
    -3.5,
    "in percentage terms",
    11.43,
    region="Stock US",
)
ZETAW = cells(
    "ZETAW",
    "Zeta Widgets Corp",
    "0.01 USD",
    2,
    "1 Share",
    0.1,
    5.0,
    "-",
    "Friday",
    -6.88,
    -3.5,
    "in percentage terms",
    50.0,
    region="Stock US",
)
ESL = cells(
    "ESL",
    "Estee Lauder Companies - Class A",
    "0.01 USD",
    2,
    "1 Share",
    0.1,
    20.0,
    "-",
    "Friday",
    -6.88,
    -3.5,
    "in percentage terms",
    80.0,
    region="Stock US",
)
SPY = cells(
    "SPY",
    "SPDR S&P 500 ETF",
    "0.01 USD",
    2,
    "1 Share",
    0.1,
    3.0,
    "12.0 USD per trade",
    "Friday",
    -6.88,
    -3.5,
    "in percentage terms",
    600.0,
    region="ETF",
)
BITQ = cells(
    "BITQ",
    "Bitwise Crypto ETF",
    "0.01 USD",
    2,
    "1 Share",
    0.1,
    4.0,
    "12.0 USD per trade",
    "-",
    "-",
    "-",
    "-",
    20.0,
    region="ETF",
)
JP = cells(
    "1605.JP",
    "Inpex Corp",
    "0.1 JPY",
    1,
    "1 share",
    1,
    None,
    "-",
    "Friday",
    -3,
    -3,
    "in percentage terms",
    "",
    region="Stock JP",
)
SHIFTED = cells(
    "SHF",
    "Shifted row",
    "0.1 JPY",
    1,
    "1 share",
    1,
    5,
    "Friday",
    -3,
    -3,
    "in percentage terms",
    "",
    1.0,
    region="Stock JP",
)
BTCXAU = cells(
    "BTCXAU",
    "Bitcoin vs Gold",
    "1e-05 XAU",
    5,
    "1 BTC",
    0.01,
    4.3099999999999996,
    "-",
    "Friday",
    -20,
    -20,
    "in percentage terms",
    30.1,
)
BUND = cells(
    "EUB10Y",
    "Euro - Bund Futures",
    "0.01 EUR",
    2,
    "1 Contract",
    1,
    3.12,
    "-",
    "-",
    "-",
    "-",
    "-",
    "129.96",
)
SHEET_ROWS: dict[str, list[dict[str, Any]]] = {
    "Forex&Metals": [EURUSD, USDTRY],
    "Commodities": [CLOIL],
    "Indices": [SP500, GER40],
    "Share_CFDs": [AAPL, AALG, ZETAW, ESL, SPY, BITQ, JP, SHIFTED],
    "Crypto": [BTCXAU],
    "Bond_CFDs": [BUND],
}


def write_xlsx(path: Path) -> Path:
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sheet, rows in SHEET_ROWS.items():
        ws = wb.create_sheet(sheet)
        head = (["Region"] if sheet == "Share_CFDs" else []) + HEADER
        ws.append(head)
        for r in rows:
            ws.append([r.get(h) for h in head])
    wb.save(path)
    from strategy_factory.data.hashing import file_sha256

    manifest = path.with_name(path.name + ".manifest.json")
    manifest.write_text(json.dumps({"sha256": file_sha256(path)}), encoding="utf-8")
    return path


def spec_row(sheet: str, c: dict[str, Any], row_no: int = 2) -> Any:
    return normalize_row(sheet, row_no, c)


def cfg() -> Any:
    return load_moneta_config(MONETA_DIR)


def us(t: dt.datetime) -> int:
    return (t - EPOCH) // dt.timedelta(microseconds=1)


def day_bars(days: list[dt.date], close: list[float]) -> dict[str, np.ndarray]:
    ts = [dt.datetime.combine(d, dt.time(), tzinfo=dt.UTC) for d in days]
    return {
        "ts": np.array([us(t) for t in ts], dtype=np.int64),
        "open": np.asarray(close, dtype=np.float64),
        "close": np.asarray(close, dtype=np.float64),
    }


# -- import (D-317, D-340) -------------------------------------------------------------------
def test_F_0_2_1_import_normalizes_every_sheet(tmp_path: Path) -> None:
    xlsx = write_xlsx(tmp_path / "spec.xlsx")
    rep = import_spec(xlsx, tmp_path / "m", source_label="spec.xlsx", file_date="2026-09-19")
    assert rep.counts == {
        "Forex&Metals": 2,
        "Commodities": 1,
        "Indices": 2,
        "Share_CFDs": 8,
        "Crypto": 1,
        "Bond_CFDs": 1,
    }
    rows = {r.broker_symbol: r for r in read_spec_csv(tmp_path / "m" / SPEC_CSV)}
    assert rows["1605.JP"].row_status == "incomplete"
    assert "spread" in rows["1605.JP"].status_reason
    assert rows["SHF"].row_status == "shifted"
    assert rows["BTCXAU"].row_status == "ok" and rows["BTCXAU"].point_value == 1e-05
    assert rows["BTCXAU"].spread_points == 4.31  # a float stored as 4.3099999999999996
    e = rows["EURUSD+"]
    assert (e.digits, e.point_size, e.contract_size, e.contract_unit) == (5, 1e-05, 1e5, "EUR")
    assert (e.quote_ccy, e.point_value, e.volume_step_lots, e.min_volume_lots) == (
        "USD",
        1.0,
        0.01,
        0.01,
    )
    assert (e.commission_model, e.commission_amount, e.commission_ccy) == ("per_lot", 6.0, "USD")
    assert (e.swap_model, e.swap_long, e.swap_short, e.triple_weekday) == (
        "points",
        -9.46,
        4.69,
        "WED",
    )
    assert rows["AAPL"].region == "Stock US" and rows["SPY"].commission_model == "per_trade"
    assert rows["CL-OIL"].swap_model == "none" and rows["CL-OIL"].triple_weekday == ""
    assert rows["USDTRY+"].triple_weekday == "THU"
    assert rows["GER40.r"].quote_ccy == "EUR"


def test_F_0_2_1_import_is_byte_identical_and_records_sha(tmp_path: Path) -> None:
    from strategy_factory.data.hashing import file_sha256

    xlsx = write_xlsx(tmp_path / "spec.xlsx")
    out = tmp_path / "m"
    import_spec(xlsx, out, source_label="spec.xlsx", file_date="2026-09-19")
    first = (out / SPEC_CSV).read_bytes()
    import_spec(xlsx, out, source_label="spec.xlsx", file_date="2026-09-19")
    assert (out / SPEC_CSV).read_bytes() == first
    meta = json.loads((out / SPEC_META).read_text(encoding="utf-8"))
    assert meta["sha256"] == file_sha256(xlsx) and meta["file_date"] == "2026-09-19"
    # a manifest with another SHA-256 is refused, and so is a missing manifest
    (tmp_path / "spec.xlsx.manifest.json").write_text(json.dumps({"sha256": "0" * 64}))
    with pytest.raises(DataError, match="does not match"):
        import_spec(xlsx, out, source_label="spec.xlsx", file_date="2026-09-19")
    (tmp_path / "spec.xlsx.manifest.json").unlink()
    with pytest.raises(DataError, match="no raw-store manifest"):
        import_spec(xlsx, out, source_label="spec.xlsx", file_date="2026-09-19")


def test_F_0_2_1_repo_broker_table_is_the_imported_file() -> None:
    meta = json.loads((MONETA_DIR / SPEC_META).read_text(encoding="utf-8"))
    assert meta["sha256"] == "f71328881a4cdcff573e169e122a78a5274d96c1de8bd968c733643a71eb6199"
    rows = read_spec_csv(MONETA_DIR / SPEC_CSV)
    regions: dict[str, int] = {}
    for r in rows:
        regions[r.region] = regions.get(r.region, 0) + 1
    assert (regions["Stock US"], regions["ETF"]) == (491, 57)  # D-524
    assert len(rows) == 1057 and sum(r.row_status == "ok" for r in rows) == 977


# -- generated profiles (hand-computed) ------------------------------------------------------
def test_F_0_2_1_fx_profile_hand_computed() -> None:
    d = profile_dict(spec_row("Forex&Metals", EURUSD), "fx", SHA, cfg())
    p = CostProfile.model_validate(d)
    assert p.status == "verified" and p.broker_symbol == "EURUSD+"
    assert p.commission.model_dump() == {
        "currency": "USD",
        "model": "per_lot",
        "lot_size": 100000.0,
        "per_lot_per_side": 3.0,
    }  # D-521: 6 USD round turn -> 3 per side
    assert p.spread.model_dump() == {"mode": "broker_scaled", "broker_spread": 2.61 * 1e-05}
    assert p.pip_size == pytest.approx(1e-4)
    assert (p.contract_size, p.volume_step, p.min_volume, p.volume_step_assumed) == (
        1e5,
        0.01,
        0.01,
        False,
    )
    sw = p.swap.model_dump()
    assert (sw["model"], sw["long"], sw["short"], sw["point_size"], sw["triple_weekday"]) == (
        "points_per_day",
        -9.46,
        4.69,
        1e-05,
        "WED",
    )
    assert (sw["rollover_time_local"], sw["rollover_tz"]) == ("17:00", "America/New_York")
    assert SHA in p.source_note and "2026-09-19" in p.source_note
    thu = profile_dict(spec_row("Forex&Metals", USDTRY), "fx", SHA, cfg())
    assert thu["swap"]["triple_weekday"] == "THU"


def test_F_0_2_1_index_profiles_and_non_usd_to_verify() -> None:
    sp = CostProfile.model_validate(
        profile_dict(spec_row("Indices", SP500), "index_cfd", SHA, cfg())
    )
    sw = sp.swap.model_dump()
    assert (sw["model"], sw["long"], sw["short"], sw["triple_weekday"]) == (
        "currency_per_lot_day",
        -1.5024,
        0.27989,
        "FRI",
    )
    assert sp.to_verify == () and (sp.contract_size, sp.volume_step) == (1.0, 0.01)
    assert sp.commission.model_dump() == {"currency": "USD", "model": "none"}
    ger = CostProfile.model_validate(
        profile_dict(spec_row("Indices", GER40), "index_cfd", SHA, cfg())
    )
    assert ger.quote_ccy == "EUR" and ger.to_verify == ("swap_non_usd_index",)  # D-321


def test_F_0_2_1_share_profile_bps_and_360_day_swap() -> None:
    d = profile_dict(spec_row("Share_CFDs", AAPL), "us_equity", SHA, cfg())
    p = CostProfile.model_validate(d)
    bps = 9.24 * 0.01 / 211.06 * 1e4  # 4.3779 bps (D-318)
    assert p.spread.model_dump() == {
        "mode": "fixed",
        "fixed": {"value": pytest.approx(bps), "unit": "bps"},
    }
    assert "quote sample 211.06" in p.source_note and "2026-09-19" in p.source_note
    sw = p.swap.model_dump()
    assert (sw["long"], sw["short"], sw["day_count"], sw["triple_weekday"]) == (
        pytest.approx(-0.0688),
        pytest.approx(-0.035),
        360,
        "FRI",
    )
    assert (p.contract_size, p.volume_step) == (1.0, 0.1)


def test_F_0_2_1_etf_profiles_per_order_and_assumed_swap() -> None:
    spy = CostProfile.model_validate(
        profile_dict(spec_row("Share_CFDs", SPY), "us_equity", SHA, cfg())
    )
    assert spy.commission.model_dump() == {"currency": "USD", "model": "per_order", "amount": 12.0}
    assert commission_params(spy) == (4, 12.0, 0.0, 0.0)
    bitq = CostProfile.model_validate(
        profile_dict(spec_row("Share_CFDs", BITQ), "us_equity", SHA, cfg())
    )
    sw = bitq.swap.model_dump()
    assert (sw["model"], sw["long"], sw["short"], sw["day_count"]) == (
        "annual_rate",
        pytest.approx(-0.0688),
        pytest.approx(-0.035),
        360,
    )  # D-322
    assert bitq.to_verify == ("swap_assumed",)


def test_F_0_2_1_no_swap_rows_and_proxy_profile() -> None:
    oil = profile_dict(spec_row("Commodities", CLOIL), "energy_cfd", SHA, cfg())
    assert oil["swap"] == {"model": "none"}
    rows = [spec_row("Share_CFDs", c) for c in (AAPL, AALG, ZETAW)]
    proxy = CostProfile.model_validate(proxy_profile_dict(rows, SHA, cfg()))
    bps = sorted(r.spread_price / r.quote_sample * 1e4 for r in rows)[1]  # median of 3
    assert proxy.status == "placeholder" and proxy.volume_step_assumed  # D-314, D-324
    assert (proxy.contract_size, proxy.volume_step, proxy.min_volume) == (1.0, 1.0, 1.0)
    assert proxy.spread.model_dump()["fixed"]["value"] == pytest.approx(bps)
    assert proxy.swap.model_dump()["day_count"] == 360


def test_F_0_2_1_commission_kernel_code_4_matches_python() -> None:
    p = CostProfile.model_validate(
        profile_dict(spec_row("Share_CFDs", SPY), "us_equity", SHA, cfg())
    )
    a = build_cost_arrays(day_bars([dt.date(2024, 1, 9)], [600.0]), p, timeframe="1D")
    for qty in (1.0, 166.6, 1e6):
        assert (
            a.commission(qty, 600.0) == 12.0 == commission_kernel(*commission_params(p), qty, 600.0)
        )


# -- D-312: swap on the mark-to-market notional ----------------------------------------------
def swap_profile(swap: dict[str, Any], **extra: Any) -> CostProfile:
    base: dict[str, Any] = {
        "name": "t",
        "status": "verified",
        "spread": {"mode": "fixed", "fixed": {"value": 0.0}},
        "commission": {"model": "none"},
        "swap": swap,
    }
    base.update(extra)
    return CostProfile.model_validate(base)


ROLL = {"rollover_time_local": "17:00", "rollover_tz": "America/New_York"}


def test_F_0_2_3_d312_annual_rate_on_changing_price_with_triple_friday() -> None:
    p = swap_profile(
        {
            "model": "annual_rate",
            "long": -0.0688,
            "short": -0.035,
            "day_count": 360,
            "triple_weekday": "FRI",
            **ROLL,
        }
    )
    days = [dt.date(2024, 1, d) for d in (10, 11, 12, 15, 16)]  # Wed Thu Fri Mon Tue
    close = [100.0, 104.0, 99.0, 101.0, 103.0]
    b = day_bars(days, close)
    a = build_cost_arrays(b, p, timeframe="1D")
    assert a.rollover_mask.tolist() == [True] * 5 and a.triple_mask.tolist() == [0, 0, 1, 0, 0]
    q = 10.0
    # held Wed..Mon (exit at Tue open): 100x1 + 104x1 + 99x3 + 101x1 = 602 price-days x 10 units
    long = round_trip_cost(a, 0, 4, q, +1, 100.0, 103.0, 0.0, 0.0, close=b["close"])
    assert long["swap"] == pytest.approx(0.0688 / 360 * 6020.0, rel=1e-12)  # 1.14667 charge
    short = round_trip_cost(a, 0, 4, q, -1, 100.0, 103.0, 0.0, 0.0, close=b["close"])
    assert short["swap"] == pytest.approx(0.035 / 360 * 6020.0, rel=1e-12)  # both sides pay
    # the superseded T06 rule (entry notional) would give 0.0688/360 x 10 x 100 x 6 days
    assert long["swap"] != pytest.approx(0.0688 / 360 * 10 * 100 * 6)


def test_F_0_2_3_d312_points_per_day_is_price_independent() -> None:
    p = swap_profile(
        {
            "model": "points_per_day",
            "long": -9.46,
            "short": 4.69,
            "point_size": 1e-05,
            "triple_weekday": "WED",
            **ROLL,
        },
        contract_size=100000.0,
    )
    b = day_bars(
        [dt.date(2024, 1, 9), dt.date(2024, 1, 10), dt.date(2024, 1, 11)], [1.10, 1.20, 1.05]
    )
    a = build_cost_arrays(b, p, timeframe="1D")
    q = 90_000.0  # 0.9 lot
    cost = round_trip_cost(a, 0, 2, q, +1, 1.10, 1.05, 0.0, 0.0, close=b["close"])
    # Tue x1 + Wed x3 = 4 days x 9.46 points x 1e-5 x 0.9 lot x 100,000 = 34.056 USD
    assert cost["swap"] == pytest.approx(9.46e-5 * q * 4, rel=1e-12)
    short = round_trip_cost(a, 0, 2, q, -1, 1.10, 1.05, 0.0, 0.0, close=b["close"])
    assert short["swap"] == pytest.approx(-4.69e-5 * q * 4, rel=1e-12)  # a credit


def test_F_0_2_3_d312_currency_per_lot_non_usd_converted_each_rollover_bar() -> None:
    p = swap_profile(
        {
            "model": "currency_per_lot_day",
            "long": -3.4908,
            "short": 0.1106,
            "triple_weekday": "FRI",
            **ROLL,
        },
        quote_ccy="EUR",
        contract_size=1.0,
    )
    b = day_bars(
        [dt.date(2024, 1, 11), dt.date(2024, 1, 12), dt.date(2024, 1, 15)],
        [16000.0, 16100.0, 15900.0],
    )
    fx = np.array([1.10, 1.09, 1.08])  # EURUSD close of each bar (D-307)
    a = build_cost_arrays(b, p, timeframe="1D")
    lots = 6.0
    cost = round_trip_cost(
        a, 0, 2, lots, +1, 16000.0, 15900.0, 0.0, 0.0, close=b["close"], fx_close=fx
    )
    # Thu x1 at 1.10 + Fri x3 at 1.09: 3.4908 EUR x 6 lots x (1.10 + 3.27) USD/EUR
    assert cost["swap"] == pytest.approx(3.4908 * 6 * (1.10 + 3 * 1.09), rel=1e-12)
    usd = round_trip_cost(a, 0, 2, lots, +1, 16000.0, 15900.0, 0.0, 0.0, close=b["close"])
    assert usd["swap"] == pytest.approx(3.4908 * 6 * 4, rel=1e-12)


def test_F_0_2_3_non_usd_spread_and_quote_commission_converted() -> None:
    p = swap_profile(
        {"model": "none"},
        quote_ccy="EUR",
        spread={"mode": "fixed", "fixed": {"value": 2.0}},
        commission={"model": "percent", "rate": 0.001, "currency": "EUR"},
    )
    b = day_bars([dt.date(2024, 1, 9), dt.date(2024, 1, 10)], [100.0, 110.0])
    a = build_cost_arrays(b, p, timeframe="1D")
    assert a.commission_in_quote
    c = round_trip_cost(
        a, 0, 1, 10.0, +1, 100.0, 110.0, 0.0, 0.0, close=b["close"], fx_close=np.array([1.1, 1.2])
    )
    assert c["spread"] == pytest.approx(1.0 * 10 * 1.1 + 1.0 * 10 * 1.2)
    assert c["commission"] == pytest.approx(0.001 * 10 * 100 * 1.1 + 0.001 * 10 * 110 * 1.2)


# -- D-315 / D-313 / D-314 sizing ------------------------------------------------------------
def test_F_0_2_1_d315_lots_floor_to_the_step() -> None:
    fx = size_lots(100_000.0, 1.0837, 100_000.0, 0.01, 0.01)  # 0.92276 lot -> 0.92
    assert (
        fx.lots == pytest.approx(0.92)
        and fx.qty == pytest.approx(92_000.0)
        and not fx.skipped_min_volume
    )
    sh = size_lots(100_000.0, 211.07, 1.0, 0.1, 0.1)  # 473.7765 shares -> 473.7
    assert sh.lots == pytest.approx(473.7) and not sh.skipped_min_volume
    assert sh.qty * 211.07 <= 100_000.0
    exact = size_lots(100_000.0, 100.0, 1.0, 0.1, 0.1)  # exactly 1000.0: float guard keeps it
    assert exact.lots == pytest.approx(1000.0)


def test_F_0_2_1_d313_below_minimum_volume_is_skipped() -> None:
    assert size_lots(100_000.0, 2_000_000.0, 1.0, 0.1, 0.1).skipped_min_volume  # 0.05 share < 0.1
    assumed = size_lots(100_000.0, 150_000.0, 1.0, 1.0, 1.0)  # D-314: step 1 share
    assert assumed.skipped_min_volume and assumed.lots == 0.0


def test_F_0_2_1_repo_profiles_volume_fields() -> None:
    p = load_profiles(REPO_COSTS)
    e = p["moneta_EURUSD+"]
    assert (e.contract_size, e.volume_step, e.min_volume, e.volume_step_assumed) == (
        1e5,
        0.01,
        0.01,
        False,
    )
    a = p["moneta_AAPL"]
    assert (a.contract_size, a.volume_step, a.volume_step_assumed) == (1.0, 0.1, False)
    proxy = p["us_share_cfd_proxy"]
    assert proxy.volume_step == 1.0 and proxy.volume_step_assumed and proxy.is_placeholder
    arr = build_cost_arrays(day_bars([dt.date(2024, 1, 9)], [211.0]), a, timeframe="1D")
    assert (arr.contract_size, arr.volume_step, arr.min_volume) == (1.0, 0.1, 0.1)
    assert not arr.volume_step_assumed


def test_F_0_2_4_cost_breakdown_shares() -> None:
    """D-350 (3): shares on charges only; a swap credit is reported, never dropped."""
    shares = cost_breakdown_shares({"spread": 2.0, "slippage": 1.0, "commission": 1.0, "swap": 4.0})
    assert shares == {
        "spread": 0.25,
        "slippage": 0.125,
        "commission": 0.125,
        "swap": 0.5,
        "swap_credit_usd": 0.0,
    }
    credit = cost_breakdown_shares(
        {"spread": 1.0, "slippage": 0.0, "commission": 1.0, "swap": -3.0}
    )
    assert credit["swap"] == 0.0 and credit["swap_credit_usd"] == 3.0  # the credit stays visible
    assert credit["spread"] == 0.5 and credit["spread"] + credit["commission"] == 1.0
    nothing = cost_breakdown_shares(
        {"spread": 0.0, "slippage": 0.0, "commission": 0.0, "swap": 0.0}
    )
    assert set(nothing.values()) == {0.0}


# -- broker_scaled spread (F-0.2.2, D-523) ---------------------------------------------------
def test_F_0_2_2_broker_scaled_hand_computed() -> None:
    p = swap_profile({"model": "none"}, spread={"mode": "broker_scaled", "broker_spread": 4e-5})
    t0 = dt.datetime(2024, 1, 9, tzinfo=dt.UTC)
    ts = [
        t0,
        t0 + dt.timedelta(days=1),
        t0 + dt.timedelta(hours=1),
        t0 + dt.timedelta(days=1, hours=1),
    ]
    dev = {"ts": np.array([us(t) for t in ts]), "spread": np.array([1e-5, 1e-5, 3e-5, 3e-5])}
    resolved, table = resolve_from_data(p, dev)
    # bar-weighted mean of the medians = 2e-5 -> scale 2; hours without data = broker spread
    assert table.full_spread[0] == pytest.approx(2e-5) and table.full_spread[1] == pytest.approx(
        6e-5
    )
    # D-350 (2): an hour without data takes the maximum of the scaled profile, not the broker
    assert table.full_spread[5] == pytest.approx(6e-5) and 5 in table.fallback_hours
    assert "22 UTC hour(s) without data filled with the profile maximum" in resolved.source_note
    hourly = np.asarray(resolved.spread.model_dump()["hourly"])
    assert np.mean(hourly[[0, 0, 1, 1]]) == pytest.approx(4e-5, rel=1e-12)
    with pytest.raises(ConfigError, match="broker_scaled"):
        build_cost_arrays(
            {"ts": dev["ts"], "open": np.ones(4), "close": np.ones(4)}, p, timeframe="1H"
        )
    fixed, _ = resolve_from_data(p, {"ts": dev["ts"]})  # no spread column: broker spread, fixed
    assert fixed.spread.model_dump() == {"mode": "fixed", "fixed": {"value": 4e-5, "unit": "price"}}


# -- mapping (D-323, D-325) -------------------------------------------------------------------
MCFG = MappingConfig(
    names_file="names.csv",
    broker_regions=("Stock US", "ETF"),
    min_name_score=0.8,
    candidate_min_score=0.6,
)
RESEARCH = {
    "EURUSD": "fx",
    "AAPL": "us_equity",
    "AAL": "us_equity",
    "SPY": "us_equity",
    "XYZ": "us_equity",
    "ESL": "us_equity",
}
NAMES = {
    "AAPL": "Apple Inc. Common Stock",
    "AAL": "American Airlines Group Inc. Common Stock",
    "XYZ": "Zeta Widgets Inc.",
    "ESL": "Esterline Technologies Corp",
}


def spec_all() -> list[Any]:
    return [
        normalize_row(s, i + 2, c) for s, rows in SHEET_ROWS.items() for i, c in enumerate(rows)
    ]


def test_F_0_9_1_mapping_rules() -> None:
    res = map_symbols(
        spec_all(),
        RESEARCH,
        NAMES,
        [{"research_symbol": "EURUSD", "broker_symbol": "EURUSD+", "note": "D-323"}],
        [{"broker_symbol": "AALG", "research_symbol": "AAL", "note": "D-524"}],
        MCFG,
    )
    mapped = {m.broker_symbol: (m.research_symbol, m.method) for m in res.mapped}
    assert mapped == {
        "EURUSD+": ("EURUSD", "manual"),
        "AAPL": ("AAPL", "ticker_exact"),
        "AALG": ("AAL", "override"),
    }
    review = {v.broker_symbol: v for v in res.review}
    assert review["ZETAW"].status == "pending_review"  # name-only: never auto-mapped
    assert review["ZETAW"].candidate_research_symbol == "XYZ"
    assert review["ESL"].reason == "ticker match, name differs"  # same ticker, other company
    # D-341: such a pair is never ticker-mapped; only a manual override can map it
    assert "ESL" not in mapped and review["ESL"].status == "pending_review"
    over = [{"broker_symbol": "ESL", "research_symbol": "ESL", "note": "confirmed by the user"}]
    forced = map_symbols(spec_all(), RESEARCH, NAMES, [], over, MCFG)
    assert ("ESL", "override") in {(m.research_symbol, m.method) for m in forced.mapped}
    assert review["SPY"].reason == "ticker match, no research name available"
    assert "SPY" not in mapped and "BITQ" not in mapped


def test_F_0_9_1_mapping_overrides_unmappable_and_duplicates() -> None:
    over = [
        {"broker_symbol": "ESL", "research_symbol": "UNMAPPABLE", "note": "Estee Lauder is EL"},
        {"broker_symbol": "ZETAW", "research_symbol": "XYZ", "note": "confirmed by user"},
        {"broker_symbol": "SPY", "research_symbol": "NOPE", "note": "x"},
    ]
    res = map_symbols(spec_all(), RESEARCH, NAMES, [], over, MCFG)
    review = {v.broker_symbol: v for v in res.review}
    assert review["ESL"].status == "unmappable" and "Estee Lauder" in review["ESL"].reason
    assert review["SPY"].status == "unmappable"  # override target not in the universe
    assert ("XYZ", "override") in {(m.research_symbol, m.method) for m in res.mapped}
    dup = [{"broker_symbol": "AALG", "research_symbol": "AAPL", "note": ""}]
    with pytest.raises(ConfigError, match="two broker symbols"):
        map_symbols(spec_all(), RESEARCH, NAMES, [], dup, MCFG)
    with pytest.raises(ConfigError, match="unknown broker symbols"):
        map_symbols(
            spec_all(),
            RESEARCH,
            NAMES,
            [],
            [{"broker_symbol": "Q", "research_symbol": "AAPL"}],
            MCFG,
        )


def test_F_0_2_1_d350_incomplete_row_never_yields_a_profile() -> None:
    """D-350 (1): an incomplete broker row gives no profile, and mapping onto one is an error."""
    jp = next(r for r in spec_all() if r.broker_symbol == "1605.JP")
    assert jp.row_status == "incomplete"
    with pytest.raises(ConfigError, match="broker row is incomplete"):
        profile_dict(jp, "us_equity", SHA, cfg())
    cfg_jp = MCFG.model_copy(update={"broker_regions": ("Stock JP",)})
    over = [{"broker_symbol": "1605.JP", "research_symbol": "AAPL", "note": "x"}]
    with pytest.raises(ConfigError, match="an incomplete row cannot yield a cost profile"):
        map_symbols(spec_all(), RESEARCH, NAMES, [], over, cfg_jp)
    # without an override it stays a review row, not a silent placeholder
    review = {
        v.broker_symbol: v for v in map_symbols(spec_all(), RESEARCH, NAMES, [], [], cfg_jp).review
    }
    assert review["1605.JP"].status == "unmappable"


def test_F_0_9_1_name_score() -> None:
    assert name_score("Apple Inc.", "Apple Inc. Common Stock") == 1.0
    assert name_score("Estee Lauder Companies - Class A", "Esterline Technologies Corp") < 0.8
    assert name_score("", "Apple") == 0.0


def test_F_0_9_1_build_end_to_end(tmp_path: Path) -> None:
    costs = tmp_path / "costs"
    shutil.copytree(REPO_COSTS, costs)
    for f in ("moneta_profiles.yaml", "assignments.yaml", "symbol_map.csv"):
        (costs / "moneta" / f).unlink()
    raw = tmp_path / "raw"
    raw.mkdir()
    with (raw / "names.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "name"])
        w.writerows(NAMES.items())
    m = yaml.safe_load((costs / "moneta" / "mapping.yaml").read_text(encoding="utf-8"))
    m["names_file"] = "names.csv"
    (costs / "moneta" / "mapping.yaml").write_text(yaml.safe_dump(m), encoding="utf-8")
    (costs / "moneta" / "symbol_overrides.csv").write_text(
        "broker_symbol,research_symbol,note\nAALG,AAL,D-524\n", encoding="utf-8"
    )
    (costs / "moneta" / "dukascopy_map.csv").write_text(
        "research_symbol,broker_symbol,note\nEURUSD,EURUSD+,D-323\n", encoding="utf-8"
    )
    import_spec(write_xlsx(tmp_path / "s.xlsx"), costs / "moneta", source_label="s", file_date="d")
    review = tmp_path / "review.csv"
    res = build(costs, raw, RESEARCH, review)
    assert {m.research_symbol for m in res.mapping.mapped} == {"EURUSD", "AAPL", "AAL"}
    profiles = load_profiles(costs)
    assert {"moneta_EURUSD+", "moneta_AAPL", "moneta_AALG", "us_share_cfd_proxy"} <= set(profiles)
    rows = list(csv.DictReader(review.open(encoding="utf-8")))
    assert {r["broker_symbol"] for r in rows} >= {"ZETAW", "ESL", "SPY", "BITQ"}


# -- repo state: coverage, universe flag, costs mandatory --------------------------------------
def test_F_0_9_1_repo_mapping_every_broker_symbol_is_mapped_or_unmappable() -> None:
    """F-0.9.1 coverage criterion (P-28 -> D-356): 548/548 mapped **or** unmappable.

    The weaker form of this test (mapped or *listed for review*) was not the criterion: a row
    still waiting for a decision proves nothing. Since the supervisor classified every review
    row, no ``pending_review`` row may remain.
    """
    spec = [r for r in read_spec_csv(MONETA_DIR / SPEC_CSV) if r.region in ("Stock US", "ETF")]
    mapped = list(csv.DictReader((MONETA_DIR / "symbol_map.csv").open(encoding="utf-8")))
    review = list(
        csv.DictReader((REPO / "docs/reviews/T06b_mapping_review.csv").open(encoding="utf-8"))
    )
    broker_symbols = {r.broker_symbol for r in spec}
    assert len(broker_symbols) == 548  # D-524: 491 US shares + 57 ETFs
    broker_mapped = {r["broker_symbol"] for r in mapped}
    unmappable = {r["broker_symbol"] for r in review if r["status"] == "unmappable"}
    pending = {r["broker_symbol"] for r in review if r["status"] != "unmappable"}
    assert pending == set(), f"still waiting for a decision: {sorted(pending)}"
    assert broker_symbols <= broker_mapped | unmappable  # 548/548 accounted for
    assert len(broker_symbols & broker_mapped) + len(broker_symbols & unmappable) == 548
    research = [r["research_symbol"] for r in mapped]
    assert len(research) == len(set(research))
    dukascopy = {r["research_symbol"] for r in mapped if r["method"] == "manual"}
    assert len(dukascopy) == 29


def test_F_0_9_1_universe_broker_flag_and_default_filter(tmp_path: Path) -> None:
    from strategy_factory.core.config import PipelineConfig, validate_config
    from strategy_factory.core.universe import load_universe

    u = load_universe(REPO / "configs" / "universe.yaml").by_symbol()
    assert u["EURUSD"].broker_symbol == "EURUSD+" and u["AAPL"].broker_symbol == "AAPL"
    assert u["USA500IDXUSD"].broker_symbol == "SP500.r" and u["AAPL"].cost_profile == "moneta_AAPL"
    assert u["AABA"].broker_symbol is None and "1D" in u["AABA"].timeframes
    cfg_ = PipelineConfig(
        universe=REPO / "configs" / "universe.yaml",
        symbols=("AABA",),
        timeframes=("1D",),
        stages=("s01_edge",),
        gates=REPO / "configs" / "gates" / "default.yaml",
    )
    assert cfg_.universe_filter == "broker"  # D-524 default
    with pytest.raises(ConfigError, match="not tradable at the broker"):
        validate_config(cfg_)
    validate_config(cfg_.model_copy(update={"universe_filter": "all"}))


def test_F_0_9_1_universe_broker_validation_errors() -> None:
    from strategy_factory.core.universe import Universe, UniverseEntry, validate_universe

    def entry(sym: str, broker: str, profile: str) -> UniverseEntry:
        return UniverseEntry(
            symbol=sym,
            asset_class="us_equity",
            reference_source="alpaca",
            timeframes=("1D",),
            cost_profile=profile,
            calendar="nyse",
            group="us_equity",
            broker_symbol=broker,
        )

    u = Universe(
        symbols=(
            entry("AAPL", "AAPL", "moneta_AAPL"),
            entry("A", "AAPL", "moneta_A"),  # duplicate broker symbol, wrong profile
            entry("AA", "NOPE", "moneta_AA"),  # unknown broker symbol
        )
    )
    problems = " | ".join(validate_universe(u, costs_dir=REPO_COSTS))
    assert "already used by AAPL" in problems
    assert "'NOPE' not an ok row" in problems
    assert "expected 'moneta_AAPL'" in problems


def test_F_0_2_1_costs_mandatory_after_moneta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assigned, missing = validate_all(
        CostsConfig(
            costs_dir=REPO_COSTS,
            universe_files=tuple(
                REPO / "configs" / "universe" / f
                for f in ("us_equity_daily.csv", "us_equity_hourly.csv", "dukascopy.csv")
            ),
        )
    )
    assert (
        not missing and assigned["AAPL"] == "moneta_AAPL" and assigned["EURUSD"] == "moneta_EURUSD+"
    )
    costs = tmp_path / "costs"
    shutil.copytree(REPO_COSTS, costs)
    path = costs / "moneta" / "moneta_profiles.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["profiles"] = [p for p in data["profiles"] if p["name"] != "moneta_AAPL"]
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.chdir(REPO)
    res = CliRunner().invoke(app, ["costs", "validate", "--costs-dir", str(costs)])
    assert res.exit_code == 1 and "moneta_AAPL" in res.output


# -- cost monotonicity with the new models (property) ------------------------------------------
DAYS = [dt.date(2024, 1, 8) + dt.timedelta(days=d) for d in range(21)]
BARS = day_bars(DAYS, [100.0 + (i % 5) for i in range(21)])
TRADES = [(0, 3, 150.0, 1), (4, 9, 80.0, -1), (10, 19, 300.0, 1)]


def total(order: float, lot_charge: float, pts: float) -> float:
    swaps = [
        {"model": "currency_per_lot_day", "long": -lot_charge, "short": -lot_charge, **ROLL},
        {"model": "points_per_day", "long": -pts, "short": -pts, "point_size": 0.01, **ROLL},
    ]
    out = 0.0
    for sw in swaps:
        p = swap_profile(sw, commission={"model": "per_order", "amount": order})
        a = build_cost_arrays(BARS, p, timeframe="1D")
        out += sum(
            round_trip_cost(a, e, x, q, d, 100.0, 100.0, 1.0, 1.0, close=BARS["close"])["total"]
            for e, x, q, d in TRADES
        )
    return out


pos = st.floats(min_value=0.0, max_value=10.0, allow_nan=False)


@settings(max_examples=examples(100), deadline=None)
@given(base=st.tuples(pos, pos, pos), which=st.integers(0, 2), bump=st.floats(1e-6, 5.0))
def test_F_0_2_4_new_models_monotone(
    base: tuple[float, float, float], which: int, bump: float
) -> None:
    raised = list(base)
    raised[which] += bump
    assert total(*raised) >= total(*base) - 1e-9
    assert not math.isnan(total(*base))


def _costs_copy(tmp_path: Path) -> Path:
    costs = tmp_path / "costs"
    shutil.copytree(REPO_COSTS, costs)
    return costs


def test_F_0_2_1_cli_moneta_import_and_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    spec = raw / cfg().source.spec_file
    spec.parent.mkdir(parents=True)
    write_xlsx(spec)
    monkeypatch.setenv("SFAC_RAW_ROOT", str(raw))
    monkeypatch.chdir(REPO)
    costs = _costs_copy(tmp_path)
    runner = CliRunner()
    res = runner.invoke(app, ["costs", "moneta", "import", "--costs-dir", str(costs)])
    assert res.exit_code == 0, res.output
    assert f"source  : {cfg().source.spec_file}" in res.output
    assert "Share_CFDs        8 rows" in res.output and "sha256  :" in res.output
    assert "shifted" in res.output and "SHF" in res.output
    outside = write_xlsx(tmp_path / "elsewhere.xlsx")
    bad = runner.invoke(
        app, ["costs", "moneta", "import", "--costs-dir", str(costs), "--xlsx", str(outside)]
    )
    assert bad.exit_code == 1 and "must be under SFAC_RAW_ROOT" in bad.output

    with (raw / "names.csv").open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows([["symbol", "name"], *NAMES.items()])
    m = yaml.safe_load((costs / "moneta" / "mapping.yaml").read_text(encoding="utf-8"))
    (costs / "moneta" / "mapping.yaml").write_text(
        yaml.safe_dump({**m, "names_file": "names.csv"}), encoding="utf-8"
    )
    (costs / "moneta" / "symbol_overrides.csv").write_text(
        "broker_symbol,research_symbol,note\nAALG,AAL,D-524\n", encoding="utf-8"
    )
    (costs / "moneta" / "dukascopy_map.csv").write_text(
        "research_symbol,broker_symbol,note\nEURUSD,EURUSD+,D-323\n", encoding="utf-8"
    )
    review = tmp_path / "review.csv"
    built = runner.invoke(
        app, ["costs", "moneta", "build", "--costs-dir", str(costs), "--review-csv", str(review)]
    )
    assert built.exit_code == 0, built.output
    assert "mapped  : 3" in built.output and review.is_file()


def test_F_0_2_1_third_currency_commission_is_refused() -> None:
    p = swap_profile(
        {"model": "none"},
        quote_ccy="EUR",
        commission={"model": "per_order", "amount": 1.0, "currency": "GBP"},
    )
    with pytest.raises(ConfigError, match="neither USD nor the quote currency"):
        build_cost_arrays(day_bars([dt.date(2024, 1, 9)], [1.0]), p, timeframe="1D")


def test_F_0_9_1_dukascopy_map_broker_symbol_listed_twice() -> None:
    twice = [
        {"research_symbol": "EURUSD", "broker_symbol": "EURUSD+"},
        {"research_symbol": "AAPL", "broker_symbol": "EURUSD+"},
    ]
    with pytest.raises(ConfigError, match="listed twice"):
        map_symbols(spec_all(), RESEARCH, NAMES, twice, [], MCFG)


# -- D-341 price check in the review CSV --------------------------------------------------------
def write_daily(
    root: Path, symbol: str, year: int, rows: list[tuple[str, float]], version: int = 1
) -> None:
    import polars as pl

    d = root / symbol
    d.mkdir(parents=True, exist_ok=True)
    name = f"{year}.parquet" if version == 1 else f"{year}.v{version}.parquet"
    pl.DataFrame({"t": [t for t, _ in rows], "c": [c for _, c in rows]}).write_parquet(d / name)


def test_F_0_9_1_raw_price_lookup(tmp_path: Path) -> None:
    from strategy_factory.data.raw_prices import last_close_on_or_before

    write_daily(
        tmp_path, "AAA", 2026, [("2026-09-17T04:00:00Z", 10.0), ("2026-09-18T04:00:00Z", 11.0)]
    )
    write_daily(tmp_path, "AAA", 2026, [("2026-09-18T04:00:00Z", 12.0)], version=2)  # newest wins
    write_daily(tmp_path, "OLD", 2019, [("2019-03-13T04:00:00Z", 122.49)])
    assert last_close_on_or_before("AAA", dt.date(2026, 9, 19), tmp_path) == (
        12.0,
        dt.date(2026, 9, 18),
    )
    assert last_close_on_or_before("OLD", dt.date(2026, 9, 19), tmp_path) == (
        122.49,
        dt.date(2019, 3, 13),
    )
    assert last_close_on_or_before("AAA", dt.date(2026, 9, 17), tmp_path) is None  # v2 starts later
    assert last_close_on_or_before("NOPE", dt.date(2026, 9, 19), tmp_path) is None


def test_F_0_9_1_review_rows_carry_the_price_check(tmp_path: Path) -> None:
    """D-341: the review CSV compares the broker quote sample with our own last close."""
    from strategy_factory.costs.moneta import ReviewRow, with_price_check

    write_daily(tmp_path, "AAPL", 2026, [("2026-09-18T04:00:00Z", 200.0)])
    rows = [
        ReviewRow("AAPL", "Stock US", "Apple Inc.", "pending_review", "AAPL", "Apple", 0.5, "x"),
        ReviewRow("ZZZ", "Stock US", "Zeta", "pending_review", "", "", None, "no match"),
    ]
    priced = with_price_check(rows, spec_all(), dt.date(2026, 9, 19), tmp_path)
    assert priced[0].broker_quote_sample == 211.06 and priced[0].research_close == 200.0
    assert priced[0].price_ratio == pytest.approx(211.06 / 200.0)
    assert priced[0].research_close_date == "2026-09-18"
    assert priced[1].price_ratio is None and priced[1].research_close_date == ""


def test_F_0_9_1_repo_review_csv_has_the_price_columns() -> None:
    rows = list(
        csv.DictReader((REPO / "docs/reviews/T06b_mapping_review.csv").open(encoding="utf-8"))
    )
    assert {"broker_quote_sample", "research_close", "research_close_date", "price_ratio"} <= set(
        rows[0]
    )
    # Since P-28 closed (D-356) every remaining row is unmappable and carries no candidate, so
    # there is nothing left to price here; the price check itself is proven on synthetic rows by
    # test_F_0_9_1_review_rows_carry_the_price_check. The invariant that survives is: a row with
    # a candidate research symbol must have been priced (or have no raw file for it).
    assert all(r["status"] == "unmappable" for r in rows)
    assert [r["broker_symbol"] for r in rows if r["candidate_research_symbol"]] == []
