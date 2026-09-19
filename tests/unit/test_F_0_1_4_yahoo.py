"""F-0.1.4: Yahoo downloader (mocked yfinance) and adapter; F-0.1.11 close-time metadata."""

from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
import polars as pl
import pytest

from strategy_factory.data.adapters.yahoo import YahooAdapter
from strategy_factory.data.config import YahooConfig
from strategy_factory.data.download import yahoo as yh
from strategy_factory.data.download.ratelimit import TLSVerificationError, TransientError
from strategy_factory.data.download.rawfiles import read_manifest
from strategy_factory.data.schema import validate_bars

REPO = Path(__file__).resolve().parents[2]
VIX = yh.AuxSeries("^VIX", "VIX", "Cboe Volatility Index", "16:15", "America/New_York", "verified")
GSPC = yh.AuxSeries("^GSPC", "SPX", "S&P 500", "", "", "to_verify")


def pandas_history(values: list[float], volume: float = 0.0) -> pd.DataFrame:
    """The shape yfinance returns: tz-aware DatetimeIndex 'Date' + OHLC/Adj Close/Volume."""
    idx = pd.DatetimeIndex(
        [
            pd.Timestamp(d, tz="America/New_York")
            for d in ("2024-03-08", "2024-03-11", "2024-11-01", "2024-11-04")
        ],
        name="Date",
    )
    return pd.DataFrame(
        {
            "Open": [v - 0.2 for v in values],
            "High": [v + 0.5 for v in values],
            "Low": [v - 0.5 for v in values],
            "Close": values,
            "Adj Close": values,
            "Volume": [volume] * len(values),
        },
        index=idx,
    )


class FakeTicker:
    calls: ClassVar[list[dict[str, Any]]] = []
    frames: ClassVar[dict[str, pd.DataFrame]] = {}

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker

    def history(self, **kwargs: Any) -> pd.DataFrame:
        FakeTicker.calls.append({"ticker": self.ticker, **kwargs})
        return FakeTicker.frames[self.ticker]


@pytest.fixture
def fake_yf(monkeypatch: pytest.MonkeyPatch) -> type[FakeTicker]:
    mod = types.ModuleType("yfinance")
    mod.Ticker = FakeTicker  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    FakeTicker.calls = []
    FakeTicker.frames = {
        "^VIX": pandas_history([14.7, 14.9, 21.9, 21.4]),
        "^GSPC": pandas_history([5123.7, 5117.1, 5728.8, 5712.7], 3.5e9),
    }
    return FakeTicker


def download(
    tmp_path: Path, today: dt.date, series: list[yh.AuxSeries] | None = None
) -> yh.YahooReport:
    return yh.run_yahoo_download(
        series or [VIX, GSPC],
        tmp_path,
        YahooConfig(),
        yh.YFinanceClient(),
        today=today,
        sleep=lambda s: None,
    )


def test_F_0_1_4_explicit_auto_adjust_false_call(tmp_path: Path, fake_yf: type[FakeTicker]) -> None:
    download(tmp_path, dt.date(2026, 9, 1))
    assert fake_yf.calls == [
        {"ticker": t, "period": "max", "interval": "1d", "auto_adjust": False, "actions": False}
        for t in ("^VIX", "^GSPC")
    ]


def test_F_0_1_4_raw_versions_are_never_overwritten(
    tmp_path: Path, fake_yf: type[FakeTicker]
) -> None:
    download(tmp_path, dt.date(2026, 9, 1))
    download(tmp_path, dt.date(2026, 9, 1))  # same day -> .v2
    download(tmp_path, dt.date(2026, 9, 2))
    names = [p.name for p in yh.raw_versions(tmp_path, "^VIX")]
    assert names == ["2026-09-01.parquet", "2026-09-01.v2.parquet", "2026-09-02.parquet"]
    first = yh.raw_versions(tmp_path, "^VIX")[0]
    m = read_manifest(first)
    assert (
        m is not None and m["client"].startswith("yfinance") and m["call"]["auto_adjust"] is False
    )
    assert len(m["sha256"]) == 64 and m["row_count"] == 4
    with pytest.raises(PermissionError):
        first.write_bytes(b"x")


def test_F_0_1_4_raw_is_stored_as_returned(tmp_path: Path, fake_yf: type[FakeTicker]) -> None:
    download(tmp_path, dt.date(2026, 9, 1), [VIX])
    raw = pl.read_parquet(yh.raw_versions(tmp_path, "^VIX")[0])
    assert raw.columns == ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
    assert raw.schema["Date"] == pl.Datetime("ns", "America/New_York")
    assert raw["Close"].to_list() == [14.7, 14.9, 21.9, 21.4]
    assert raw["Date"].dt.date().to_list()[0] == dt.date(2024, 3, 8)  # instant kept (pandas unit)


def test_F_0_1_4_revision_diff_is_reported(tmp_path: Path, fake_yf: type[FakeTicker]) -> None:
    download(tmp_path, dt.date(2026, 9, 1), [VIX])
    fake_yf.frames["^VIX"] = pandas_history([14.7, 15.1, 21.9, 21.4])  # one revised close
    rep = download(tmp_path, dt.date(2026, 9, 2), [VIX])
    assert rep.revisions and rep.revisions[0]["changed_rows"] == 1
    assert rep.revisions[0]["max_abs_diff"] == pytest.approx(0.2)
    report = pl.read_csv(tmp_path / "_reports" / "yahoo_revisions.csv")
    assert report["changed_rows"].to_list() == [1]


def test_F_0_1_4_retry_and_tls_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Flaky:
        library_version = "fake"

        def __init__(self, errors: list[Exception]) -> None:
            self.errors = errors

        def history(self, ticker: str, params: dict[str, Any]) -> pl.DataFrame:
            if self.errors:
                raise self.errors.pop(0)
            return yh.pandas_history_to_polars(pandas_history([1.0, 1.1, 1.2, 1.3]))

    rep = yh.run_yahoo_download(
        [VIX], tmp_path, YahooConfig(), Flaky([TransientError("429")]), sleep=lambda s: None
    )
    assert rep.stored == ["^VIX"]
    with pytest.raises(TLSVerificationError):
        yh.run_yahoo_download(
            [VIX], tmp_path, YahooConfig(), Flaky([TLSVerificationError("x")]), sleep=lambda s: None
        )


def test_F_0_1_4_adapter_daily_stamps_and_metadata(
    tmp_path: Path, fake_yf: type[FakeTicker]
) -> None:
    download(tmp_path, dt.date(2026, 9, 1))
    path = yh.latest_raw(tmp_path, "^VIX")
    assert path is not None
    df, meta = YahooAdapter().to_canonical(
        [path],
        ticker="^VIX",
        symbol="VIX",
        close_time_local="16:15",
        close_tz="America/New_York",
        close_time_status="verified",
    )
    # session dates at 00:00 UTC on both sides of the US DST switches (2024-03-10, 2024-11-03)
    assert df["ts"].to_list() == [
        dt.datetime(2024, m, d, tzinfo=dt.UTC) for m, d in ((3, 8), (3, 11), (11, 1), (11, 4))
    ]
    assert (meta.source, meta.price_type, meta.adjustment, meta.volume_quality) == (
        "yahoo",
        "trade",
        "raw",
        "none",
    )
    assert (meta.timeframe, meta.bar_label, meta.original_tz) == ("1D", "start", "America/New_York")
    assert (meta.value_final_time_local, meta.value_final_tz, meta.value_final_status) == (
        "16:15",
        "America/New_York",
        "verified",
    )
    assert meta.asset_class == "aux" and "auto_adjust=False" in meta.notes
    assert validate_bars(df, meta) == []

    gspc = yh.latest_raw(tmp_path, "^GSPC")
    assert gspc is not None
    _, gmeta = YahooAdapter().to_canonical([gspc], ticker="^GSPC", symbol="SPX")
    assert gmeta.volume_quality == "partial"
    assert (gmeta.value_final_time_local, gmeta.value_final_tz, gmeta.value_final_status) == (
        None,
        None,
        "to_verify",
    )


def test_F_0_1_4_adapter_uses_close_not_adj_close(
    tmp_path: Path, fake_yf: type[FakeTicker]
) -> None:
    frame = pandas_history([10.0, 11.0, 12.0, 13.0])
    frame["Adj Close"] = [9.0, 10.0, 11.0, 12.0]
    fake_yf.frames["^VIX"] = frame
    download(tmp_path, dt.date(2026, 9, 1), [VIX])
    df, _ = YahooAdapter().to_canonical(
        [yh.latest_raw(tmp_path, "^VIX")], ticker="^VIX", symbol="VIX"
    )  # type: ignore[list-item]
    assert df["close"].to_list() == [10.0, 11.0, 12.0, 13.0]


def test_F_0_1_11_aux_universe_close_times() -> None:
    series = yh.load_aux_universe(REPO / "configs" / "universe" / "aux_yahoo.csv")
    assert [s.ticker for s in series] == [
        "^VIX",
        "DX-Y.NYB",
        "^TNX",
        "^GSPC",
        "^NDX",
        "^RUT",
        "^DJI",
    ]
    for s in series:
        assert s.close_time_status in {"verified", "to_verify"}
        if s.close_time_status == "verified":
            assert s.close_time_local and s.close_tz and s.notes  # verified needs a cited source
        else:
            assert s.close_time_local == ""  # no guessed times


def test_F_0_1_4_tls_error_logged_by_yfinance_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """yfinance logs the curl TLS failure and returns an empty frame: must still STOP."""
    import logging

    class LoggingTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def history(self, **kwargs: Any) -> pd.DataFrame:
            logging.getLogger("yfinance").error(
                "Failed to get ticker '%s' reason: Failed to perform, curl: (60) SSL certificate "
                "OpenSSL verify result: unable to get local issuer certificate (20).",
                self.ticker,
            )
            return pd.DataFrame()

    mod = types.ModuleType("yfinance")
    mod.Ticker = LoggingTicker  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    with pytest.raises(TLSVerificationError, match="unable to get local issuer certificate"):
        yh.run_yahoo_download(
            [VIX], tmp_path, YahooConfig(), yh.YFinanceClient(), sleep=lambda s: None
        )
    assert not list(tmp_path.rglob("*.parquet"))


def test_F_0_1_11_unverified_extra_lag_config() -> None:
    from strategy_factory.data.config import load_aux_config

    path = REPO / "configs" / "data" / "aux_series.yaml"
    assert path.is_file()
    cfg = load_aux_config(path)
    assert cfg.aux.unverified_extra_lag_days == 1
