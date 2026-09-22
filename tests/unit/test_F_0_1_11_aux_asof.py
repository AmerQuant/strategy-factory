"""F-0.1.11 / F-0.1.4 (T04m): aux series next to a traded symbol -- the as-of join, the guard that
keeps them out of the candidate set, their ingest and their schedule checks.

D-014 (as-of, extra lag for unverified close times), D-718 (verified close times), D-719 (the
staleness cap in traded sessions), D-720 (each aux series on its own calendar), addendum §5.3.
"""

from __future__ import annotations

import datetime as dt
import zoneinfo
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
from fixtures.bars import make_meta
from fixtures.t05 import FAKE_HASH, MemoryLedger
from typer.testing import CliRunner

from strategy_factory.cli import app
from strategy_factory.core.errors import DataError, HoldoutAccessError
from strategy_factory.data.auxiliary import (
    AuxView,
    aux_calendar_of,
    build_view,
    final_instants,
    nyse_calendar,
)
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import AuxAsOfConfig, AuxConfig, QualityConfig, SplitConfig
from strategy_factory.data.download import yahoo as yh
from strategy_factory.data.schedule import expected_aux
from strategy_factory.data.schema import SeriesMetadata
from strategy_factory.data.split import HOLDOUT_STAGE, DataAccess, SplitManager
from strategy_factory.data.store import SnapshotStore

REPO = Path(__file__).resolve().parents[2]
SESSIONS = REPO / "configs" / "calendars" / "nyse_sessions.csv"
CLOSURES = REPO / "configs" / "calendars" / "us_bond_market_closures.csv"
NY = zoneinfo.ZoneInfo("America/New_York")
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)


def _nyse_days() -> list[dt.date]:
    cal = nyse_calendar(SESSIONS)
    return [dt.date(1970, 1, 1) + dt.timedelta(days=int(d)) for d in cal.days]


NYSE_DAYS = _nyse_days()


def us(t: dt.datetime) -> int:
    return (t - EPOCH) // dt.timedelta(microseconds=1)


def midnight(d: dt.date) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(0), tzinfo=dt.UTC)


def code(d: dt.date) -> float:
    return float(d.year * 10000 + d.month * 100 + d.day)


def aux_meta(**over: Any) -> SeriesMetadata:
    base: dict[str, Any] = {
        "source": "yahoo",
        "source_symbol": "^VIX",
        "symbol": "VIX",
        "asset_class": "aux",
        "adjustment": "raw",
        "session": "exchange",
        "feed": "none",
        "volume_quality": "none",
        "original_tz": "America/Chicago",
        "value_final_time_local": "16:15",
        "value_final_tz": "America/New_York",
        "value_final_status": "verified",
        "notes": "aux_calendar=nyse",
        "snapshot_hash": FAKE_HASH,
    }
    base.update(over)
    return make_meta(**base)


SPX = {
    "symbol": "SPX",
    "source_symbol": "^GSPC",
    "original_tz": "America/New_York",
    "value_final_time_local": None,
    "value_final_tz": None,
    "value_final_status": "to_verify",
}
DXY = {
    "symbol": "DXY",
    "source_symbol": "DX-Y.NYB",
    "original_tz": "America/New_York",
    "value_final_time_local": "19:15",
    "notes": "aux_calendar=weekdays",
}
EQUITY = make_meta(symbol="AAPL", source_symbol="AAPL", snapshot_hash=FAKE_HASH)
FX_1D = make_meta(
    source="dukascopy",
    symbol="EURUSD",
    source_symbol="EURUSD",
    asset_class="fx",
    price_type="mid",
    adjustment="raw",
    session="24x5",
    feed="none",
    volume_quality="partial",
    original_tz="UTC",
    snapshot_hash=FAKE_HASH,
)
FX_1H = FX_1D.model_copy(update={"timeframe": "1H"})
EQUITY_1H = EQUITY.model_copy(update={"timeframe": "1H"})


def aux_arrays(days: list[dt.date]) -> dict[str, np.ndarray]:
    c = np.array([code(d) for d in days])
    return {
        "ts": np.array([us(midnight(d)) for d in days], dtype=np.int64),
        "open": c,
        "high": c,
        "low": c,
        "close": c,
    }


def join(
    meta: SeriesMetadata,
    days: list[dt.date],
    traded: SeriesMetadata,
    traded_ts: list[dt.datetime],
    stale: int = 5,
) -> AuxView:
    return build_view(
        meta,
        aux_arrays(days),
        traded,
        np.array([us(t) for t in traded_ts], dtype=np.int64),
        extra_lag_days=1,
        max_stale_sessions=stale,
        sessions_file=SESSIONS,
    )


def used(view: AuxView) -> list[float]:
    """The aux value (its date as yyyymmdd) each traded bar reads; NaN = none."""
    return [float(v) for v in view.at_bars(view.close)]


def sessions_between(a: dt.date, b: dt.date) -> list[dt.date]:
    return [d for d in NYSE_DAYS if a <= d <= b]


def weekdays_between(a: dt.date, b: dt.date) -> list[dt.date]:
    return [
        a + dt.timedelta(days=i)
        for i in range((b - a).days + 1)
        if (a + dt.timedelta(days=i)).weekday() < 5
    ]


VIX_DAYS = sessions_between(dt.date(2024, 1, 2), dt.date(2024, 12, 31))
D = dt.date


# -- the addendum §5.3 examples -------------------------------------------------------------
def test_F_0_1_11_equity_at_the_close_of_d_sees_vix_of_d_minus_1() -> None:
    days = sessions_between(D(2024, 3, 11), D(2024, 3, 15))
    v = join(aux_meta(), VIX_DAYS, EQUITY, [midnight(d) for d in days])
    assert used(v) == [20240308, 20240311, 20240312, 20240313, 20240314]


def test_F_0_1_11_fx_daily_of_d_sees_vix_of_d() -> None:
    days = weekdays_between(D(2024, 3, 11), D(2024, 3, 15))
    v = join(aux_meta(), VIX_DAYS, FX_1D, [midnight(d) for d in days])
    assert used(v) == [20240311, 20240312, 20240313, 20240314, 20240315]


def test_F_0_1_11_every_value_read_is_final_strictly_before_the_decision() -> None:
    days = sessions_between(D(2024, 1, 2), D(2024, 12, 31))
    v = join(aux_meta(), VIX_DAYS, EQUITY, [midnight(d) for d in days])
    ok = v.idx >= 0
    assert not ok[0] and ok[1:].all()  # the first session has no earlier VIX in this series
    assert (v.final_us[v.idx[ok]] < v.decision_us[ok]).all()


# -- verified close times, DST, early closes (D-718) -----------------------------------------
def test_F_0_1_11_dxy_19_15_new_york_crosses_the_fx_day_end_with_dst() -> None:
    """DXY is final at 19:15 New York. The FX day ends at 24:00 UTC: 20:00 EDT in summer (DXY of
    d is usable) but 19:00 EST in winter (it is not yet: d-1)."""
    meta = aux_meta(**DXY)
    aux_days = weekdays_between(D(2024, 1, 1), D(2024, 12, 31))
    summer = weekdays_between(D(2024, 7, 8), D(2024, 7, 12))
    assert used(join(meta, aux_days, FX_1D, [midnight(d) for d in summer])) == [
        code(d) for d in summer
    ]
    winter = weekdays_between(D(2024, 1, 8), D(2024, 1, 12))
    assert used(join(meta, aux_days, FX_1D, [midnight(d) for d in winter])) == [
        20240105,
        20240108,
        20240109,
        20240110,
        20240111,
    ]


def test_F_0_1_11_early_close_uses_the_real_close() -> None:
    """2024-11-29 and 2024-07-03 close at 13:00: VIX of that day (16:15) is not usable."""
    v = join(aux_meta(), VIX_DAYS, EQUITY, [midnight(D(2024, 7, 3)), midnight(D(2024, 11, 29))])
    assert used(v) == [20240702, 20241127]


def test_F_0_1_11_unverified_close_time_is_24h_local_plus_one_day() -> None:
    """SPX (to_verify, D-718): final at 24:00 New York + 1 day, so Wednesday reads Monday."""
    days = sessions_between(D(2024, 3, 11), D(2024, 3, 15))
    v = join(aux_meta(**SPX), VIX_DAYS, EQUITY, [midnight(d) for d in days])
    assert used(v) == [20240308, 20240308, 20240311, 20240312, 20240313]


def test_F_0_1_11_final_instants_in_the_series_zone() -> None:
    ts = np.array([us(midnight(D(2024, 3, 8)))], dtype=np.int64)
    vix = final_instants(ts, aux_meta(), 1)[0]
    assert vix == us(dt.datetime(2024, 3, 8, 16, 15, tzinfo=NY))
    tnx = final_instants(ts, aux_meta(**{**SPX, "original_tz": "America/Chicago"}), 1)[0]
    chicago = zoneinfo.ZoneInfo("America/Chicago")
    assert tnx == us(dt.datetime(2024, 3, 10, 0, 0, tzinfo=chicago))  # 24:00 Fri + 1 day
    with pytest.raises(DataError, match="final instant is undefined"):
        final_instants(ts, aux_meta(**{**SPX, "original_tz": "unknown"}), 1)


# -- intraday consumers ---------------------------------------------------------------------
def test_F_0_1_11_hourly_bars_equity_and_fx() -> None:
    eq = [dt.datetime(2024, 3, 13, h, tzinfo=NY).astimezone(dt.UTC) for h in range(9, 16)]
    assert set(used(join(aux_meta(), VIX_DAYS, EQUITY_1H, eq))) == {20240312}
    # FX 19:00 UTC ends 20:00 UTC = 16:00 EDT (< 16:15): VIX of d-1; 20:00 UTC ends 21:00: d
    fx = [dt.datetime(2024, 3, 13, 19, tzinfo=dt.UTC), dt.datetime(2024, 3, 13, 20, tzinfo=dt.UTC)]
    assert used(join(aux_meta(), VIX_DAYS, FX_1H, fx)) == [20240312, 20240313]
    # a Sunday hour belongs to Monday's session (D-010) and reads Friday's VIX
    sunday = [dt.datetime(2024, 3, 10, 22, tzinfo=dt.UTC)]
    assert used(join(aux_meta(), VIX_DAYS, FX_1H, sunday)) == [20240308]


# -- staleness in traded sessions (D-719) ----------------------------------------------------
def test_F_0_1_11_staleness_counts_traded_sessions() -> None:
    gap = set(sessions_between(D(2024, 3, 11), D(2024, 3, 19)))  # 7 sessions without VIX
    aux_days = [d for d in VIX_DAYS if d not in gap]
    days = sessions_between(D(2024, 3, 8), D(2024, 3, 22))
    v = join(aux_meta(), aux_days, EQUITY, [midnight(d) for d in days], stale=5)
    got = dict(zip(days, used(v), strict=True))
    assert got[D(2024, 3, 8)] == 20240307
    # VIX of Fri 03-08 is final 16:15, after Friday's close: usable from Monday 03-11 (age 0)
    for d in sessions_between(D(2024, 3, 11), D(2024, 3, 18)):  # ages 0..5
        assert got[d] == 20240308
    assert np.isnan(got[D(2024, 3, 19)]) and np.isnan(got[D(2024, 3, 20)])  # ages 6, 7
    assert got[D(2024, 3, 21)] == 20240320 and got[D(2024, 3, 22)] == 20240321
    tighter = join(aux_meta(), aux_days, EQUITY, [midnight(d) for d in days], stale=2)
    assert np.isnan(dict(zip(days, used(tighter), strict=True))[D(2024, 3, 14)])  # age 3


def test_F_0_1_11_staleness_does_not_depend_on_the_window_start() -> None:
    gap = set(sessions_between(D(2024, 3, 11), D(2024, 3, 19)))
    aux_days = [d for d in VIX_DAYS if d not in gap]
    full = sessions_between(D(2024, 3, 1), D(2024, 3, 22))
    late = sessions_between(D(2024, 3, 18), D(2024, 3, 22))
    a = dict(
        zip(
            full, used(join(aux_meta(), aux_days, EQUITY, [midnight(d) for d in full])), strict=True
        )
    )
    b = dict(
        zip(
            late, used(join(aux_meta(), aux_days, EQUITY, [midnight(d) for d in late])), strict=True
        )
    )
    for d in late:
        assert (np.isnan(a[d]) and np.isnan(b[d])) or a[d] == b[d]


def test_F_0_1_11_nothing_after_the_last_decision_is_returned() -> None:
    days = sessions_between(D(2024, 3, 11), D(2024, 3, 15))
    v = join(aux_meta(), VIX_DAYS, EQUITY, [midnight(d) for d in days])
    assert v.final_us.max() < v.decision_us.max()
    assert float(v.close[-1]) == 20240314  # VIX of 03-15 (final 16:15) is after 03-15's close


def test_F_0_1_11_indicator_on_aux_bars_read_at_idx() -> None:
    """A filter computes on the aux bars and reads at idx (not over repeated values)."""
    eq = [dt.datetime(2024, 3, 13, h, tzinfo=NY).astimezone(dt.UTC) for h in range(9, 16)]
    v = join(aux_meta(), VIX_DAYS, EQUITY_1H, eq)
    sma2 = np.convolve(v.close, np.ones(2) / 2, mode="full")[: v.close.size]
    assert set(v.at_bars(sma2).tolist()) == {(20240311 + 20240312) / 2}
    with pytest.raises(DataError, match="one entry per aux bar"):
        v.at_bars(np.ones(3))


def test_F_0_1_11_aux_calendar_note() -> None:
    assert aux_calendar_of("raw prices; aux_calendar=nyse_bond; unit=percent") == "nyse_bond"
    assert aux_calendar_of("raw prices") is None
    assert aux_calendar_of("aux_calendar=moon") is None


# -- through the store: the guard, the development read, the holdout (T04m) ------------------
def _snapshot(
    store: SnapshotStore, cat: Catalog, meta: SeriesMetadata, days: list[dt.date]
) -> None:
    n = len(days)
    close = np.array([code(d) for d in days]) if meta.asset_class == "aux" else 100.0 + np.arange(n)
    df = pl.DataFrame(
        {
            "ts": [midnight(d) for d in days],
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": np.zeros(n) if meta.asset_class == "aux" else np.full(n, 1000.0),
        }
    ).with_columns(pl.col("ts").cast(pl.Datetime("us", "UTC")))
    stored = cat.register(store.write_snapshot(df, meta.model_copy(update={"snapshot_hash": None})))
    cat.set_reference(meta.symbol, meta.timeframe, stored.snapshot_hash or "")


@pytest.fixture
def world(tmp_path: Path) -> tuple[SplitManager, MemoryLedger]:
    store, cat = SnapshotStore(tmp_path), Catalog(tmp_path)
    _snapshot(store, cat, EQUITY, sessions_between(D(2018, 1, 2), D(2024, 12, 31)))
    msft = EQUITY.model_copy(update={"symbol": "MSFT", "source_symbol": "MSFT"})
    _snapshot(store, cat, msft, sessions_between(D(2018, 1, 2), D(2024, 12, 31)))
    _snapshot(store, cat, aux_meta(), sessions_between(D(2016, 1, 4), D(2025, 6, 30)))
    ledger = MemoryLedger()
    cfg = AuxConfig(aux=AuxAsOfConfig(sessions_file=SESSIONS))
    return SplitManager(ledger, SplitConfig(), store, cat, aux_config=cfg), ledger


def test_F_0_1_11_aux_is_never_a_candidate(world: tuple[SplitManager, MemoryLedger]) -> None:
    mgr, ledger = world
    access = DataAccess(mgr)
    for call in (
        lambda: access.bars("VIX", "1D"),
        lambda: access.arrays("VIX", "1D"),
        lambda: access.split("VIX", "1D"),
        lambda: mgr.open_holdout("c1", "VIX", "1D", stage=HOLDOUT_STAGE),
    ):
        with pytest.raises(DataError, match="auxiliary series"):
            call()
    assert not ledger.splits and not ledger.accesses and not ledger.snapshots


def test_F_0_1_11_development_read_ends_at_dev_end(
    world: tuple[SplitManager, MemoryLedger],
) -> None:
    mgr, ledger = world
    access = DataAccess(mgr)
    v = access.aux("VIX", "AAPL", "1D")
    split = access.split("AAPL", "1D")
    dev = access.arrays("AAPL", "1D")
    assert v.idx.shape == dev["ts"].shape and (v.idx >= 0).all()
    assert int(v.decision_us.max()) == us(
        dt.datetime.combine(split.dev_end.date(), dt.time(16), tzinfo=NY)
    )
    assert int(v.final_us.max()) < int(v.decision_us.max())  # nothing beyond the window
    assert v.key.symbol == "VIX" and v.traded.symbol == "AAPL"
    assert [k.symbol for k in ledger.splits] == ["AAPL"]  # no split for VIX
    with pytest.raises(DataError, match="not an auxiliary series"):
        access.aux("MSFT", "AAPL", "1D")
    with pytest.raises(DataError, match="is an auxiliary series"):  # VIX as the traded symbol
        access.aux("MSFT", "VIX", "1D")


def test_F_0_1_11_holdout_read_inside_the_one_shot_access(
    world: tuple[SplitManager, MemoryLedger],
) -> None:
    mgr, ledger = world
    with pytest.raises(HoldoutAccessError):
        mgr.open_holdout_with_inputs("c1", "AAPL", "1D", aux=("VIX",), stage="s05_filter")
    with pytest.raises(DataError, match="not an auxiliary series"):  # validated before spending
        mgr.open_holdout_with_inputs("c1", "AAPL", "1D", aux=("MSFT",), stage=HOLDOUT_STAGE)
    with pytest.raises(DataError, match="aux input of itself"):
        mgr.open_holdout_with_inputs("c1", "AAPL", "1D", aux=("AAPL",), stage=HOLDOUT_STAGE)
    assert not ledger.accesses
    bars, conv, views = mgr.open_holdout_with_inputs(
        "c1", "AAPL", "1D", aux=("VIX",), stage=HOLDOUT_STAGE
    )
    assert conv == {} and list(ledger.accesses) == ["c1"]  # one access, the candidate's
    v = views["VIX"]
    assert v.idx.shape == (bars.height,) and (v.idx >= 0).all()
    last_close = dt.datetime.combine(bars["ts"].max().date(), dt.time(16), tzinfo=NY)
    assert int(v.final_us.max()) < us(last_close)
    assert [k.symbol for k in ledger.splits] == ["AAPL"]
    with pytest.raises(HoldoutAccessError):
        mgr.open_holdout_with_inputs("c1", "AAPL", "1D", aux=("VIX",), stage=HOLDOUT_STAGE)


# -- schedule checks on the aux series' own calendars (D-720) --------------------------------
def test_F_0_1_11_aux_schedule_calendars() -> None:
    cfg = QualityConfig(sessions_file=SESSIONS, bond_closures_file=CLOSURES)
    lo, hi = midnight(D(2016, 10, 3)), midnight(D(2016, 11, 18))
    nyse = expected_aux(lo, hi, "aux_calendar=nyse", cfg).starts
    bond = expected_aux(lo, hi, "aux_calendar=nyse_bond", cfg).starts
    week = expected_aux(lo, hi, "aux_calendar=weekdays", cfg).starts
    assert nyse is not None and bond is not None and week is not None
    closures = {midnight(D(2016, 10, 10)), midnight(D(2016, 11, 11))}
    assert set(nyse.to_list()) - set(bond.to_list()) == closures
    assert set(week.to_list()) >= set(nyse.to_list()) and week.len() == 35
    none = expected_aux(lo, hi, "raw prices", cfg)
    assert none.starts is None and "D-720" in none.reason


def test_F_0_1_11_bond_closures_follow_the_rule() -> None:
    rows = pl.read_csv(CLOSURES)["date"].str.to_date().to_list()
    assert D(2017, 11, 10) not in rows and D(2023, 11, 10) not in rows  # Saturday: no closure
    assert D(2018, 11, 12) in rows  # Sunday -> Monday
    assert all(d in set(NYSE_DAYS) for d in rows)


# -- the aux universe file (D-718, D-720) ----------------------------------------------------
def test_F_0_1_11_aux_universe_close_time_provenance() -> None:
    series = {
        s.symbol: s for s in yh.load_aux_universe(REPO / "configs" / "universe" / "aux_yahoo.csv")
    }
    assert {k for k, s in series.items() if s.close_time_status == "verified"} == {
        "VIX",
        "DXY",
        "NDX",
    }
    assert (series["DXY"].close_time_local, series["NDX"].close_time_local) == ("19:15", "17:15")
    for s in series.values():
        assert s.close_time_source and s.close_time_checked  # every entry says where / when
        dt.date.fromisoformat(s.close_time_checked)
    assert {s.symbol: s.calendar for s in series.values()} == {
        "VIX": "nyse", "DXY": "weekdays", "TNX": "nyse_bond", "SPX": "nyse",
        "NDX": "nyse", "RUT": "nyse", "DJI": "nyse",
    }  # fmt: skip
    assert series["TNX"].value_unit == "percent"


def test_F_0_1_11_aux_universe_rejects_a_bad_calendar(tmp_path: Path) -> None:
    path = tmp_path / "aux.csv"
    path.write_text(
        "ticker,symbol,description,close_time_local,close_tz,close_time_status,calendar\n"
        "^X,X,x,,,to_verify,moon\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="D-720"):
        yh.load_aux_universe(path)


# -- ingest (T04m) ---------------------------------------------------------------------------
class FakeClient:
    library_version = "fake 1.0"

    def history(self, ticker: str, params: dict[str, Any]) -> pl.DataFrame:
        days = sessions_between(D(2024, 3, 1), D(2024, 3, 15))
        c = [code(d) for d in days]
        return pl.DataFrame(
            {
                "Date": [dt.datetime.combine(d, dt.time(0), tzinfo=NY) for d in days],
                "Open": c,
                "High": c,
                "Low": c,
                "Close": c,
                "Adj Close": c,
                "Volume": [0] * len(days),
            }
        )


@pytest.fixture
def ingest_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw, store = tmp_path / "raw", tmp_path / "store"
    udir = tmp_path / "universe"
    udir.mkdir()
    (udir / "aux_yahoo.csv").write_text(
        "ticker,symbol,description,close_time_local,close_tz,close_time_status,calendar,"
        "value_unit,close_time_source,close_time_checked,notes\n"
        "^VIX,VIX,vix,16:15,America/New_York,verified,nyse,index points,Cboe,2026-09-19,\n",
        encoding="utf-8",
    )
    (udir / "us_equity_daily.csv").write_text(
        "symbol,source_of_listing\nAAPL,x\n", encoding="utf-8"
    )
    cfg = tmp_path / "yahoo.yaml"
    cfg.write_text(f"universe_file: {(udir / 'aux_yahoo.csv').as_posix()}\n", encoding="utf-8")
    monkeypatch.setenv("SFAC_RAW_ROOT", str(raw))
    monkeypatch.setenv("SFAC_DATA_ROOT", str(store))
    series = yh.load_aux_universe(udir / "aux_yahoo.csv")
    yh.run_yahoo_download(series, raw, yh.YahooConfig(), FakeClient(), sleep=lambda s: None)
    return tmp_path


def _ingest(env: Path, *extra: str) -> Any:
    return CliRunner().invoke(
        app, ["data", "ingest", "yahoo", "--config", str(env / "yahoo.yaml"), *extra]
    )


def test_F_0_1_4_T04m_ingest_reference_only_when_asked_and_idempotent(ingest_env: Path) -> None:
    out = _ingest(ingest_env)
    assert out.exit_code == 0, out.output
    cat = Catalog(ingest_env / "store")
    assert not cat.has_reference("VIX", "1D")  # no reference without --set-reference
    meta = cat.list_snapshots("VIX", "1D")
    assert meta.height == 1
    notes = meta["notes"][0]
    assert "aux_calendar=nyse" in notes and "close time checked 2026-09-19" in notes
    assert _ingest(ingest_env, "--set-reference").exit_code == 0
    assert cat.has_reference("VIX", "1D")
    events = cat.events().height
    again = _ingest(ingest_env, "--set-reference")
    assert again.exit_code == 0 and "(reference)" in again.output
    assert cat.events().height == events and cat.list_snapshots("VIX", "1D").height == 1


def test_F_0_1_4_T04m_ingest_refuses_a_tradeable_symbol(ingest_env: Path) -> None:
    csv_path = ingest_env / "universe" / "us_equity_daily.csv"
    csv_path.write_text("symbol,source_of_listing\nVIX,x\n", encoding="utf-8")
    out = _ingest(ingest_env)
    assert out.exit_code == 1 and "tradeable universe symbols" in out.output
    assert not (ingest_env / "store").exists() or Catalog(ingest_env / "store").table().height == 0


def test_F_0_1_11_no_aux_value_final_in_the_window() -> None:
    """Found by the leakage property: an aux series that starts after the window gives -1 at every
    bar (not an error)."""
    days = sessions_between(D(2024, 1, 3), D(2024, 1, 5))
    v = join(aux_meta(), [D(2024, 1, 12)], EQUITY, [midnight(d) for d in days])
    assert v.close.size == 0 and (v.idx == -1).all()
