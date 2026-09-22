"""Yahoo auxiliary daily series via yfinance (T04c, F-0.1.4).

* ``yfinance`` (pinned) is always called with explicit ``auto_adjust=False`` and
  ``actions=False``, daily bars, full history (``period="max"``).
* Every run writes a new immutable raw file per ticker (Yahoo history can be revised):
  ``<raw>/aux/yahoo/1D/<SAFE_TICKER>/<download_date>.parquet`` (``.vN`` for a second run on
  the same day) plus a manifest with the yfinance version, call parameters and sha256. All
  versions are kept.
* The frame is stored as returned (columns and values unchanged; the pandas index becomes
  the ``Date`` column with its time zone), converted to Polars at this edge.
* A new version is compared with the previous one; differing rows are reported in
  ``_reports/yahoo_revisions.csv`` (warning only).
* Polite: a pause between tickers, retries with backoff on transient errors; certificate
  errors stop the run (verification is never disabled).
"""

from __future__ import annotations

import csv
import datetime as dt
import functools
import io
import logging
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import polars as pl

from strategy_factory.core.errors import ConfigError
from strategy_factory.core.logging import get_logger
from strategy_factory.data.config import YahooConfig
from strategy_factory.data.download.ratelimit import (
    GaveUpError,
    TLSVerificationError,
    TransientError,
    call_with_retry,
)
from strategy_factory.data.download.rawfiles import (
    next_version_path,
    read_manifest,
    versions,
    write_immutable,
)
from strategy_factory.data.store import safe_component

log = get_logger(__name__)

RAW_SUBDIR = ("aux", "yahoo", "1D")
SUFFIX = ".parquet"
PRICE_COLS = ("Open", "High", "Low", "Close", "Adj Close", "Volume")
TLS_MARKERS = (
    "certificate verify failed",
    "SSL certificate",
    "CERTIFICATE_VERIFY_FAILED",
    "CertificateVerifyError",
    "unable to get local issuer certificate",
    "curl: (60)",
)


@dataclass(frozen=True)
class AuxSeries:
    ticker: str
    symbol: str
    description: str
    close_time_local: str
    close_tz: str
    close_time_status: str
    calendar: str = ""  # nyse | nyse_bond | weekdays (D-720)
    value_unit: str = ""
    close_time_source: str = ""  # D-718: where the close time was verified (or why not)
    close_time_checked: str = ""  # D-718: the date it was checked
    notes: str = ""


AUX_CALENDARS = ("nyse", "nyse_bond", "weekdays")


def load_aux_universe(path: Path) -> list[AuxSeries]:
    if not path.is_file():
        raise ConfigError("aux universe file not found", config_path=path)
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    series = [
        AuxSeries(**{k: r.get(k, "") or "" for k in AuxSeries.__dataclass_fields__}) for r in rows
    ]
    bad = [s.ticker for s in series if s.calendar not in AUX_CALENDARS]
    if bad:
        raise ConfigError(
            f"aux series without a valid calendar {AUX_CALENDARS} (D-720): {bad}", config_path=path
        )
    return series


class HistoryClient(Protocol):
    """Daily history of one ticker as a Polars frame (index as a ``Date`` column)."""

    def history(self, ticker: str, params: dict[str, Any]) -> pl.DataFrame: ...

    @property
    def library_version(self) -> str: ...


class YFinanceClient:
    """yfinance wrapper; pandas is used only here, at the edge."""

    def __init__(self) -> None:
        import importlib.metadata

        import yfinance

        self._yf = yfinance
        self._version = importlib.metadata.version("yfinance")

    @property
    def library_version(self) -> str:
        return f"yfinance {self._version}"

    def history(self, ticker: str, params: dict[str, Any]) -> pl.DataFrame:
        # yfinance often logs transport errors (incl. TLS) and returns an empty frame instead of
        # raising, so its log records are captured and checked as well.
        capture = _Capture()
        yf_log = logging.getLogger("yfinance")
        yf_log.addHandler(capture)
        try:
            pdf = self._yf.Ticker(ticker).history(**params)
        except Exception as exc:  # yfinance wraps transport errors in several types
            _raise_if_tls(ticker, str(exc), exc)
            raise TransientError(f"{ticker}: {type(exc).__name__}: {str(exc)[:200]}") from exc
        finally:
            yf_log.removeHandler(capture)
        if pdf is None or len(pdf) == 0:
            _raise_if_tls(ticker, " | ".join(capture.messages))
            return pl.DataFrame()
        return pandas_history_to_polars(pdf)


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _raise_if_tls(ticker: str, text: str, cause: BaseException | None = None) -> None:
    if any(m.lower() in text.lower() for m in TLS_MARKERS):
        raise TLSVerificationError(f"TLS verification failed for {ticker}: {text[:300]}") from cause


def pandas_history_to_polars(pdf: Any) -> pl.DataFrame:
    """yfinance history frame -> Polars without pyarrow (values and time zone unchanged).

    The DatetimeIndex becomes the ``Date`` column (nanoseconds, original time zone); the
    remaining columns are taken as NumPy arrays in their original order.
    """
    idx = pdf.index
    tz = str(idx.tz) if getattr(idx, "tz", None) is not None else None
    date = pl.Series(idx.name or "Date", idx.as_unit("ns").asi8).cast(pl.Datetime("ns"))
    if tz is not None:
        date = date.dt.replace_time_zone("UTC").dt.convert_time_zone(tz)
    cols = [pl.Series(str(c), pdf[c].to_numpy()) for c in pdf.columns]
    return pl.DataFrame([date, *cols])


def ticker_dir(raw_root: Path, ticker: str) -> Path:
    return raw_root.joinpath(*RAW_SUBDIR, safe_component(ticker.replace("^", "_")))


def raw_versions(raw_root: Path, ticker: str) -> list[Path]:
    """All stored versions of a ticker, oldest first (date base, then .vN)."""
    d = ticker_dir(raw_root, ticker)
    if not d.is_dir():
        return []
    bases = sorted({p.name.split(".")[0] for p in d.iterdir() if p.name.endswith(SUFFIX)})
    return [v for b in bases for v in versions(d, b, SUFFIX)]


@dataclass
class YahooReport:
    stored: list[str] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)
    revisions: list[dict[str, Any]] = field(default_factory=list)


VALUE_COLS = ("Open", "High", "Low", "Close", "Adj Close")


def revision_diff(previous: pl.DataFrame, current: pl.DataFrame) -> dict[str, Any]:
    """Rows of ``previous`` whose values changed in ``current`` (on the common dates)."""
    key = "Date"
    cols = [c for c in VALUE_COLS if c in previous.columns and c in current.columns]
    j = previous.join(current, on=key, how="inner", suffix="_new")
    if j.height == 0 or not cols:
        return {"common_rows": 0, "changed_rows": 0, "max_abs_diff": 0.0}
    diffs = [(pl.col(f"{c}_new") - pl.col(c)).abs().fill_null(0.0).alias(c) for c in cols]
    d = j.select(diffs)
    changed = d.select(pl.any_horizontal([pl.col(c) > 0 for c in cols]).sum()).item()
    mx = d.select(pl.max_horizontal([pl.col(c).max() for c in cols])).item()
    return {
        "common_rows": j.height,
        "changed_rows": int(changed or 0),
        "max_abs_diff": float(mx or 0.0),
        "removed_rows": previous.height - j.height,
        "added_rows": current.height - j.height,
    }


def write_revision_report(raw_root: Path, rows: list[dict[str, Any]]) -> Path:
    path = raw_root / "_reports" / "yahoo_revisions.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["checked_at", "ticker", "previous", "current", "common_rows", "changed_rows",
            "max_abs_diff", "removed_rows", "added_rows"]  # fmt: skip
    new = not path.is_file()
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)
    return path


def run_yahoo_download(
    series: Sequence[AuxSeries],
    raw_root: Path,
    cfg: YahooConfig,
    client: HistoryClient,
    today: dt.date | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> YahooReport:
    today = today or dt.datetime.now(dt.UTC).date()
    params = cfg.call_params()
    report = YahooReport()
    for i, s in enumerate(series):
        if i:
            sleep(cfg.pause_seconds)
        try:
            df = call_with_retry(
                functools.partial(client.history, s.ticker, params),
                cfg.retry.max_retries,
                cfg.retry.backoff_base_seconds,
                cfg.retry.backoff_max_seconds,
                sleep=sleep,
                rng=rng,
            )
        except GaveUpError as exc:
            log.error("yahoo %s failed: %s", s.ticker, exc)
            report.failed.append({"ticker": s.ticker, "error": str(exc)})
            continue
        if df.height == 0:
            report.failed.append({"ticker": s.ticker, "error": "empty response"})
            continue
        previous = raw_versions(raw_root, s.ticker)
        buf = io.BytesIO()
        df.write_parquet(buf, compression="zstd")
        target = next_version_path(ticker_dir(raw_root, s.ticker), today.isoformat(), SUFFIX)
        manifest = {
            "source": "yahoo",
            "ticker": s.ticker,
            "client": client.library_version,
            "call": {"method": "Ticker.history", **params},
            "downloaded_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "row_count": df.height,
            "columns": df.columns,
        }
        path = write_immutable(target, buf.getvalue(), manifest)
        report.stored.append(s.ticker)
        if previous:
            diff = revision_diff(pl.read_parquet(previous[-1]), df)
            row = {"checked_at": manifest["downloaded_at"], "ticker": s.ticker,
                   "previous": previous[-1].name, "current": path.name, **diff}  # fmt: skip
            report.revisions.append(row)
            if diff["changed_rows"]:
                log.warning(
                    "yahoo %s: %d revised rows vs %s (max |diff| %.6g)",
                    s.ticker,
                    diff["changed_rows"],
                    previous[-1].name,
                    diff["max_abs_diff"],
                )
        log.info("yahoo %s: %d rows -> %s", s.ticker, df.height, path.name)
    if report.revisions:
        write_revision_report(raw_root, report.revisions)
    return report


def latest_raw(raw_root: Path, ticker: str) -> Path | None:
    v = raw_versions(raw_root, ticker)
    return v[-1] if v else None


def manifest_of(path: Path) -> dict[str, Any]:
    return read_manifest(path) or {}
