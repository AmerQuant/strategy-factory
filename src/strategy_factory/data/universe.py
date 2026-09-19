"""US-equity universe files for the Alpaca downloads (T04a).

* ``us_equity_daily.csv``: every symbol of the raw MS-US-1D copy
  (``SFAC_RAW_ROOT/us_equity/alpaca_sip_all/1D/us_<SYM>.csv``). MarketScanner wrote file
  names with ``.``, ``/`` -> ``_`` (and dropped ``^``); US tickers contain no ``_``, so
  ``_`` maps back to ``.`` (``us_BRK_B.csv`` -> ``BRK.B``).
* ``us_equity_hourly.csv``: S&P 500 point-in-time members since ``history_start`` + ETFs.
  Membership comes from the fja05680/sp500 dataset ("S&P 500 Historical Components &
  Changes", one row per change date with the full comma-separated ticker list) -- the same
  source and method MarketScanner used. The downloaded CSV is stored immutably under
  ``SFAC_RAW_ROOT/reference/sp500_pit/``. ETFs are the ``etfs``, ``indices`` and
  ``commodities`` rows of the MarketScanner ``symbols.csv`` raw copy.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

import polars as pl

from strategy_factory.core.errors import DataError
from strategy_factory.data.download.ratelimit import TLSVerificationError
from strategy_factory.data.download.rawfiles import next_version_path, write_immutable
from strategy_factory.data.hashing import file_sha256

PIT_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/" + urllib.parse.quote(
    "S&P 500 Historical Components & Changes (Updated).csv"
)
ETF_SLUGS = ("etfs", "indices", "commodities")
DAILY_RAW_DIR = ("us_equity", "alpaca_sip_all", "1D")
PIT_RAW_DIR = ("reference", "sp500_pit")


def daily_symbols(raw_root: Path) -> list[tuple[str, str]]:
    """(symbol, source_of_listing) from the MS-US-1D raw copy file names."""
    d = raw_root.joinpath(*DAILY_RAW_DIR)
    if not d.is_dir():
        raise DataError(f"MS-US-1D raw copy not found: {d}")
    out = []
    for p in sorted(d.glob("us_*.csv")):
        out.append((p.stem[3:].replace("_", "."), f"ms_us_1d:{p.name}"))
    return out


def fetch_pit_csv(raw_root: Path, timeout: float = 60.0) -> Path:
    """Download the PIT membership CSV into the raw store (new immutable version).

    Uses the standard library with default certificate verification (the platform trust
    store); a certificate failure raises :class:`TLSVerificationError`.
    """
    req = urllib.request.Request(PIT_URL, headers={"User-Agent": "strategy-factory"})
    try:
        with urllib.request.urlopen(
            req, timeout=timeout, context=ssl.create_default_context()
        ) as r:
            payload = r.read()
    except ssl.SSLCertVerificationError as exc:
        raise TLSVerificationError(f"TLS verification failed for {PIT_URL}: {exc}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise TLSVerificationError(f"TLS verification failed for {PIT_URL}: {exc}") from exc
        raise
    target = next_version_path(
        raw_root.joinpath(*PIT_RAW_DIR), f"fja05680_sp500_{dt.date.today():%Y%m%d}", ".csv"
    )
    return write_immutable(
        target,
        payload,
        {
            "source": "github.com/fja05680/sp500",
            "url": PIT_URL,
            "downloaded_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "method": "urllib (stdlib), default certificate verification",
        },
    )


def pit_members(pit_csv: Path, start: dt.date) -> pl.DataFrame:
    """(symbol, first_member_date, last_member_date) for members on/after ``start``.

    The snapshot in force on ``start`` (the last change date before it) counts from
    ``start``; ``last_member_date`` is the last snapshot date that lists the ticker (for
    current members: the dataset's latest date).
    """
    raw = pl.read_csv(pit_csv, schema_overrides={"date": pl.Utf8, "tickers": pl.Utf8})
    snaps = raw.select(pl.col("date").str.to_date("%Y-%m-%d"), "tickers").sort("date")
    before = snaps.filter(pl.col("date") < start).tail(1).with_columns(pl.lit(start).alias("date"))
    window = pl.concat([before, snaps.filter(pl.col("date") >= start)])
    if window.height == 0:
        raise DataError(f"no membership snapshots on or after {start}")
    long = window.with_columns(pl.col("tickers").str.split(",")).explode(
        "tickers", empty_as_null=True
    )
    long = long.with_columns(pl.col("tickers").str.strip_chars().alias("symbol")).filter(
        pl.col("symbol") != ""
    )
    return (
        long.group_by("symbol")
        .agg(
            pl.col("date").min().alias("first_member_date"),
            pl.col("date").max().alias("last_member_date"),
        )
        .sort("symbol")
    )


def etf_symbols(symbols_csv: Path) -> list[str]:
    df = pl.read_csv(symbols_csv, infer_schema_length=0)
    sel = df.filter(pl.col("market_slug").is_in(list(ETF_SLUGS)))
    return sorted(set(sel["source_ticker"].to_list()))


def _write_csv(
    path: Path, header: list[str], rows: list[list[str]], meta: dict[str, object]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    meta_path = path.with_name(path.name + ".meta.json")
    meta_path.write_text(
        json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8", newline="\n"
    )


def build_daily_universe(raw_root: Path, out: Path) -> int:
    rows = daily_symbols(raw_root)
    _write_csv(
        out,
        ["symbol", "source_of_listing"],
        [[s, src] for s, src in rows],
        {
            "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "source": str(raw_root.joinpath(*DAILY_RAW_DIR)),
            "method": "file names us_<SYM>.csv; '_' mapped back to '.'",
            "symbols": len(rows),
        },
    )
    return len(rows)


def build_hourly_universe(
    pit_csv: Path, symbols_csv: Path, start: dt.date, out: Path
) -> dict[str, int]:
    members = pit_members(pit_csv, start)
    etfs = [e for e in etf_symbols(symbols_csv) if e not in set(members["symbol"].to_list())]
    rows = [
        [
            r["symbol"],
            "sp500_pit",
            r["first_member_date"].isoformat(),
            r["last_member_date"].isoformat(),
        ]
        for r in members.iter_rows(named=True)
    ] + [[e, "etf", "", ""] for e in etfs]
    _write_csv(
        out,
        ["symbol", "reason", "first_member_date", "last_member_date"],
        rows,
        {
            "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "history_start": start.isoformat(),
            "pit_source": {"file": str(pit_csv), "sha256": file_sha256(pit_csv), "url": PIT_URL},
            "etf_source": {
                "file": str(symbols_csv),
                "sha256": file_sha256(symbols_csv),
                "market_slugs": list(ETF_SLUGS),
            },
            "method": (
                "snapshot in force on history_start plus every change snapshot after it; "
                "union of tickers; first/last snapshot date per ticker (first clipped to "
                "history_start; last = dataset's latest date for current members)"
            ),
            "sp500_pit": members.height,
            "etf": len(etfs),
        },
    )
    return {"sp500_pit": members.height, "etf": len(etfs)}
