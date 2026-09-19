"""Alpaca SIP bar downloader (T04a, F-0.1.2).

* Thin client wrapper around **alpaca-py** (:class:`AlpacaPyClient`); everything else talks
  to the :class:`BarsClient` protocol, so the SDK can be swapped and tests use mocks.
* ``feed=SIP``, ``adjustment=SPLIT``; one calendar year per request, many symbols per request.
* Every HTTP request (including SDK pagination) takes a token from a :class:`TokenBucket`
  that keeps any 60 s window within the configured budget. Retries (429/5xx/network) use
  exponential backoff with jitter; after ``max_retries`` the batch is logged as failed and
  the download continues. Certificate errors stop the download (verification is never
  disabled).
* Raw output is immutable: ``<raw>/us_equity/alpaca_sip_split/<tf>/<SYMBOL>/<YEAR>.parquet``
  holds Alpaca's JSON bar fields exactly as returned (``t`` as the RFC-3339 UTC string,
  ``o h l c v n vw``) with a ``.manifest.json`` (request, time, rows, sha256, completeness).
  A (symbol, year) chunk whose manifest says ``complete`` is skipped on re-runs; an
  incomplete (current) year is re-downloaded into a new version file.
* Credentials come only from ``ALPACA_API_KEY`` / ``ALPACA_API_SECRET`` (environment or
  ``.env``) and are never logged.
"""

from __future__ import annotations

import csv
import datetime as dt
import functools
import io
import random
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import polars as pl

from strategy_factory.core.env import resolve_env
from strategy_factory.core.errors import ConfigError
from strategy_factory.core.logging import get_logger
from strategy_factory.data.config import AlpacaConfig
from strategy_factory.data.download.ratelimit import (
    GaveUpError,
    PermanentError,
    TLSVerificationError,
    TokenBucket,
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

KEY_ENV = "ALPACA_API_KEY"
SECRET_ENV = "ALPACA_API_SECRET"
TIMEFRAMES = ("1D", "1H")
RAW_SUBDIR = ("us_equity", "alpaca_sip_split")
RAW_SCHEMA: dict[str, pl.DataType] = {
    "t": pl.Utf8(),
    "o": pl.Float64(),
    "h": pl.Float64(),
    "l": pl.Float64(),
    "c": pl.Float64(),
    "v": pl.Float64(),
    "n": pl.Int64(),
    "vw": pl.Float64(),
}
SUFFIX = ".parquet"

RawBars = dict[str, list[dict[str, Any]]]


class BarsClient(Protocol):
    """Minimal market-data client: bars for many symbols over ``[start, end]``."""

    def get_bars(
        self, symbols: Sequence[str], timeframe: str, start: dt.datetime, end: dt.datetime
    ) -> RawBars: ...

    @property
    def library_version(self) -> str: ...


@dataclass(frozen=True)
class Credentials:
    key: str
    secret: str

    def __repr__(self) -> str:  # never leak the values
        return "Credentials(key=***, secret=***)"


def load_credentials() -> Credentials:
    env = resolve_env((KEY_ENV, SECRET_ENV))
    key, secret = env[KEY_ENV][0], env[SECRET_ENV][0]
    if not key or not secret:
        raise ConfigError(
            f"{KEY_ENV} and {SECRET_ENV} must be set (environment or .env); no other source is used"
        )
    return Credentials(key, secret)


class AlpacaPyClient:
    """alpaca-py ``StockHistoricalDataClient`` with a budgeted HTTP session."""

    def __init__(self, credentials: Credentials, bucket: TokenBucket, config: AlpacaConfig) -> None:
        import importlib.metadata

        import requests
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        self._version = importlib.metadata.version("alpaca-py")
        self._requests = requests
        self._request_cls = StockBarsRequest
        self._tf = {"1D": TimeFrame.Day, "1H": TimeFrame.Hour}
        self._feed = DataFeed.SIP
        self._adjustment = Adjustment.SPLIT
        client = StockHistoricalDataClient(credentials.key, credentials.secret, raw_data=True)

        class _BudgetedSession(requests.Session):
            def request(self, *args: Any, **kwargs: Any) -> Any:
                bucket.acquire()
                return super().request(*args, **kwargs)

        # one token per real HTTP request (pagination included); our retry policy only
        client._session = _BudgetedSession()
        client._retry = 0
        self._client = client

    @property
    def library_version(self) -> str:
        return f"alpaca-py {self._version}"

    def get_bars(
        self, symbols: Sequence[str], timeframe: str, start: dt.datetime, end: dt.datetime
    ) -> RawBars:
        from alpaca.common.exceptions import APIError

        req = self._request_cls(
            symbol_or_symbols=list(symbols),
            timeframe=self._tf[timeframe],
            start=start,
            end=end,
            adjustment=self._adjustment,
            feed=self._feed,
        )
        try:
            raw = self._client.get_stock_bars(req)
        except self._requests.exceptions.SSLError as exc:
            raise TLSVerificationError(f"TLS certificate verification failed: {exc}") from exc
        except (
            self._requests.exceptions.ConnectionError,
            self._requests.exceptions.Timeout,
        ) as exc:
            raise TransientError(f"network error: {type(exc).__name__}") from exc
        except APIError as exc:
            status = exc.status_code
            if status == 429 or (status is not None and status >= 500):
                raise TransientError(f"HTTP {status}", status) from exc
            raise PermanentError(f"HTTP {status}: {exc}", status) from exc
        return {k: list(v) for k, v in dict(raw).items()}


# --------------------------------------------------------------------------------------
# Raw chunk files
# --------------------------------------------------------------------------------------
def chunk_dir(raw_root: Path, timeframe: str, symbol: str) -> Path:
    return raw_root.joinpath(*RAW_SUBDIR, timeframe, safe_component(symbol))


def chunk_bounds(year: int, start: dt.date, end: dt.date) -> tuple[dt.datetime, dt.datetime, bool]:
    """UTC request window for ``year`` clipped to [start, end]; ``full`` if it spans the year."""
    y0 = dt.datetime(year, 1, 1, tzinfo=dt.UTC)
    y1 = dt.datetime(year + 1, 1, 1, tzinfo=dt.UTC)
    lo = max(y0, dt.datetime.combine(start, dt.time(), tzinfo=dt.UTC))
    hi = min(y1, dt.datetime.combine(end + dt.timedelta(days=1), dt.time(), tzinfo=dt.UTC))
    return lo, hi, lo == y0 and hi == y1


def is_chunk_complete(raw_root: Path, timeframe: str, symbol: str, year: int) -> bool:
    d = chunk_dir(raw_root, timeframe, symbol)
    for p in versions(d, str(year), SUFFIX):
        m = read_manifest(p)
        if m and m.get("complete"):
            return True
    return False


def latest_chunks(raw_root: Path, timeframe: str, symbol: str) -> list[Path]:
    """Latest version of every year file for ``symbol`` (the adapter's input)."""
    d = chunk_dir(raw_root, timeframe, symbol)
    if not d.is_dir():
        return []
    bases = sorted({p.name.split(".")[0] for p in d.iterdir() if p.name.endswith(SUFFIX)})
    return [versions(d, b, SUFFIX)[-1] for b in bases]


def bars_to_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Alpaca raw JSON bars -> frame with the JSON fields unchanged (extra keys kept)."""
    if not rows:
        return pl.DataFrame(schema=RAW_SCHEMA)
    df = pl.DataFrame(rows, infer_schema_length=None)
    casts = [pl.col(c).cast(t) for c, t in RAW_SCHEMA.items() if c in df.columns]
    return df.with_columns(casts)


def write_chunk(
    raw_root: Path,
    timeframe: str,
    symbol: str,
    year: int,
    rows: list[dict[str, Any]],
    request: dict[str, Any],
    complete: bool,
    library_version: str,
) -> Path:
    df = bars_to_frame(rows)
    buf = io.BytesIO()
    df.write_parquet(buf, compression="zstd")
    target = next_version_path(chunk_dir(raw_root, timeframe, symbol), str(year), SUFFIX)
    manifest = {
        "source": "alpaca",
        "symbol": symbol,
        "timeframe": timeframe,
        "year": year,
        "request": request,
        "client": library_version,
        "downloaded_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "row_count": df.height,
        "complete": complete,
    }
    return write_immutable(target, buf.getvalue(), manifest)


# --------------------------------------------------------------------------------------
# Download run
# --------------------------------------------------------------------------------------
@dataclass
class DownloadReport:
    timeframe: str
    requested_symbols: int = 0
    chunks_written: int = 0
    chunks_skipped: int = 0
    rows_written: int = 0
    failed_batches: list[dict[str, Any]] = field(default_factory=list)
    missing_symbols: list[str] = field(default_factory=list)


def batched(items: Sequence[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield list(items[i : i + size])


def symbol_has_rows(raw_root: Path, timeframe: str, symbol: str) -> bool:
    for p in latest_chunks(raw_root, timeframe, symbol):
        m = read_manifest(p)
        if m and m.get("row_count", 0) > 0:
            return True
    return False


def write_missing_report(raw_root: Path, timeframe: str, rows: list[dict[str, str]]) -> Path:
    """Merge ``rows`` into ``_reports/alpaca_missing_<tf>.csv`` (one row per symbol)."""
    path = raw_root / "_reports" / f"alpaca_missing_{timeframe}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict[str, str]] = {}
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as fh:
            existing = {r["symbol"]: r for r in csv.DictReader(fh)}
    for r in rows:
        existing[r["symbol"]] = r
    cols = ["symbol", "timeframe", "start", "end", "checked_at", "reason"]
    tmp = path.with_name(path.name + ".partial")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for sym in sorted(existing):
            w.writerow(existing[sym])
    tmp.replace(path)
    return path


def _log_retry(timeframe: str, year: int, attempt: int, exc: Exception, delay: float) -> None:
    log.warning(
        "alpaca %s %s: retry %d after %s (sleep %.1fs)", timeframe, year, attempt, exc, delay
    )


def run_download(
    client: BarsClient,
    symbols: Sequence[str],
    timeframe: str,
    start: dt.date,
    end: dt.date,
    raw_root: Path,
    config: AlpacaConfig,
    now: dt.datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> DownloadReport:
    """Download ``symbols`` for ``[start, end]`` year by year; resumable and immutable."""
    if timeframe not in TIMEFRAMES:
        raise ConfigError(f"timeframe must be one of {TIMEFRAMES}, got {timeframe!r}")
    now = now or dt.datetime.now(dt.UTC)
    report = DownloadReport(timeframe=timeframe, requested_symbols=len(symbols))
    size = config.batch_size[timeframe]
    for year in range(start.year, end.year + 1):
        lo, hi, full_year = chunk_bounds(year, start, end)
        complete = full_year and hi <= now
        pending = [s for s in symbols if not is_chunk_complete(raw_root, timeframe, s, year)]
        report.chunks_skipped += len(symbols) - len(pending)
        for batch in batched(pending, size):
            request = {
                "symbols": batch,
                "timeframe": timeframe,
                "start": lo.isoformat(),
                "end": (hi - dt.timedelta(seconds=1)).isoformat(),
                "feed": config.feed,
                "adjustment": config.adjustment,
            }

            def call(
                batch: list[str] = batch, lo: dt.datetime = lo, hi: dt.datetime = hi
            ) -> RawBars:
                return client.get_bars(batch, timeframe, lo, hi - dt.timedelta(seconds=1))

            try:
                data = call_with_retry(
                    call,
                    config.retry.max_retries,
                    config.retry.backoff_base_seconds,
                    config.retry.backoff_max_seconds,
                    sleep=sleep,
                    rng=rng,
                    on_retry=functools.partial(_log_retry, timeframe, year),
                )
            except (GaveUpError, PermanentError) as exc:
                log.error(
                    "alpaca %s %s: batch of %d symbols failed: %s", timeframe, year, len(batch), exc
                )
                report.failed_batches.append({"year": year, "symbols": batch, "error": str(exc)})
                continue
            for sym in batch:
                rows = data.get(sym, [])
                write_chunk(
                    raw_root, timeframe, sym, year, rows, request, complete, client.library_version
                )
                report.chunks_written += 1
                report.rows_written += len(rows)
            log.info("alpaca %s %s: %d symbols written", timeframe, year, len(batch))

    failed = {s for b in report.failed_batches for s in b["symbols"]}
    stamp = now.isoformat(timespec="seconds")
    missing = [
        s for s in symbols if s not in failed and not symbol_has_rows(raw_root, timeframe, s)
    ]
    report.missing_symbols = missing
    if missing:
        write_missing_report(
            raw_root,
            timeframe,
            [
                {
                    "symbol": s,
                    "timeframe": timeframe,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "checked_at": stamp,
                    "reason": "no bars returned (delisted before start, renamed, or never listed)",
                }
                for s in missing
            ],
        )
    return report


def make_client(config: AlpacaConfig) -> AlpacaPyClient:
    bucket = TokenBucket(config.rate_limit.requests_per_minute, config.rate_limit.burst)
    return AlpacaPyClient(load_credentials(), bucket, config)
