"""F-0.1.2 (T04a): universe files -- daily from the raw copy, hourly from PIT list + ETFs."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from strategy_factory.data.universe import (
    build_daily_universe,
    build_hourly_universe,
    daily_symbols,
    etf_symbols,
    pit_members,
)

PIT = """date,tickers
2015-06-01,"AAPL,OLD1,BRK.B"
2015-12-15,"AAPL,OLD1,BRK.B,MSFT"
2017-03-01,"AAPL,BRK.B,MSFT,NEW1"
2020-01-02,"AAPL,BRK.B,MSFT,NEW1,NEW2"
2021-06-01,"AAPL,BRK.B,NEW2,NEW3"
"""


def test_F_0_1_2_pit_members_since_start(tmp_path: Path) -> None:
    p = tmp_path / "pit.csv"
    p.write_text(PIT, encoding="utf-8")
    m = {
        r["symbol"]: (r["first_member_date"], r["last_member_date"])
        for r in pit_members(p, dt.date(2016, 1, 1)).iter_rows(named=True)
    }
    start = dt.date(2016, 1, 1)
    assert m["OLD1"] == (start, start)  # member on the start date, removed 2017-03-01
    assert m["MSFT"] == (start, dt.date(2020, 1, 2))
    assert m["NEW1"] == (dt.date(2017, 3, 1), dt.date(2020, 1, 2))
    assert m["AAPL"] == (start, dt.date(2021, 6, 1))
    assert "BRK.B" in m and "NEW3" in m


def test_F_0_1_2_daily_symbols_map_underscore_back_to_dot(tmp_path: Path) -> None:
    d = tmp_path / "us_equity" / "alpaca_sip_all" / "1D"
    d.mkdir(parents=True)
    for name in ("us_AAPL.csv", "us_BRK_B.csv", "us_ALL_PRH.csv", "other.csv"):
        (d / name).write_text("date,close\n", encoding="utf-8")
    assert daily_symbols(tmp_path) == [
        ("AAPL", "ms_us_1d:us_AAPL.csv"),
        ("ALL.PRH", "ms_us_1d:us_ALL_PRH.csv"),
        ("BRK.B", "ms_us_1d:us_BRK_B.csv"),
    ]
    n = build_daily_universe(tmp_path, tmp_path / "u" / "us_equity_daily.csv")
    assert n == 3 and (tmp_path / "u" / "us_equity_daily.csv.meta.json").is_file()


def test_F_0_1_2_hourly_universe_with_etfs(tmp_path: Path) -> None:
    pit = tmp_path / "pit.csv"
    pit.write_text(PIT, encoding="utf-8")
    sym = tmp_path / "symbols.csv"
    sym.write_text(
        "source_ticker,market_slug\nSPY,etfs\nGLD,commodities\nEWJ,indices\nAAPL,us-stocks\nSPY,indices\n",
        encoding="utf-8",
    )
    assert etf_symbols(sym) == ["EWJ", "GLD", "SPY"]
    out = tmp_path / "us_equity_hourly.csv"
    counts = build_hourly_universe(pit, sym, dt.date(2016, 1, 1), out)
    assert counts == {"sp500_pit": 7, "etf": 3}
    df = pl.read_csv(out, infer_schema_length=0)
    assert df.columns == ["symbol", "reason", "first_member_date", "last_member_date"]
    assert df.filter(pl.col("symbol") == "SPY")["reason"].to_list() == ["etf"]
