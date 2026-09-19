"""T00 / F-0.1.12 -- read-only inventory of the market data already on disk.

Walks the source data folders, groups files by naming scheme / layout / columns and
writes a factual report:

* ``docs/data_inventory.md``   -- human-readable, one section per group
* ``docs/data_inventory.json`` -- the same facts, one object per group

READ-ONLY: source files are only ever opened for reading ("rb" / polars readers).
Every file under every source root is stat-ed (size + mtime) before and after the
run and the two snapshots are compared; the result is written into the report.

Run (no project environment):

    uv run --no-project --python 3.12 --with polars --with pyarrow --with pandas \
        python scripts/data_inventory.py

Source roots default to the sibling ``SourceCodes`` tree of this repository
(``<repo>/../SourceCodes/...``); override with ``--quantplatform``,
``--marketscanner``, ``--marketedge`` and ``--dukascopy``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import statistics
import sys
import time
import traceback
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

# --------------------------------------------------------------------------------------
# Scan parameters (inventory-script constants, not framework decision numbers)
# --------------------------------------------------------------------------------------
MAX_DEEP_FILES = 50  # per-file statistics stop after this many files per group (task rule)
BIG_CSV_BYTES = 500 * 1024 * 1024  # CSVs above this are sampled (first/last N lines)
BIG_CSV_SAMPLE_LINES = 200_000
GAP_MULTIPLE = 3  # "missing bars" = gap larger than 3x the timeframe inside a session
BIG_MOVE = 0.30  # |close/prev_close - 1| above this is reported as a large jump
HEAD_ROWS = 5
TAIL_ROWS = 3

# Known forward splits used as adjustment probes: (ticker, first date at new price, ratio)
SPLIT_PROBES: list[tuple[str, dt.date, float]] = [
    ("AAPL", dt.date(2020, 8, 31), 4.0),
    ("TSLA", dt.date(2020, 8, 31), 5.0),
    ("NVDA", dt.date(2021, 7, 20), 4.0),
    ("AMZN", dt.date(2022, 6, 6), 20.0),
    ("GOOGL", dt.date(2022, 7, 18), 20.0),
    ("TSLA", dt.date(2022, 8, 25), 3.0),
    ("WMT", dt.date(2024, 2, 26), 3.0),
    ("NVDA", dt.date(2024, 6, 10), 10.0),
    ("CMG", dt.date(2024, 6, 26), 50.0),
    ("AVGO", dt.date(2024, 7, 15), 10.0),
    ("SMCI", dt.date(2024, 10, 1), 10.0),
]
# Tickers used for cross-source price/volume comparisons (dividend payers + index ETF)
CROSS_TICKERS = ["AAPL", "MSFT", "SPY", "KO", "XOM", "JPM", "T"]
# NYSE full-day closures used to test the daily calendar
US_HOLIDAYS = [
    dt.date(2020, 11, 26),
    dt.date(2021, 12, 24),
    dt.date(2022, 6, 20),
    dt.date(2023, 4, 7),
    dt.date(2024, 7, 4),
    dt.date(2024, 12, 25),
    dt.date(2025, 1, 9),
    dt.date(2025, 4, 18),
]
US_HALF_DAYS = [dt.date(2023, 11, 24), dt.date(2024, 11, 29), dt.date(2024, 12, 24)]

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SRC = REPO.parent / "SourceCodes"
NY = "America/New_York"
WARSAW = "Europe/Warsaw"
UTC = "UTC"


# --------------------------------------------------------------------------------------
# Small read-only I/O helpers
# --------------------------------------------------------------------------------------
def read_head_lines(path: Path, n: int) -> list[str]:
    out: list[str] = []
    with path.open("rb") as fh:
        for raw in fh:
            out.append(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
            if len(out) >= n:
                break
    return out


def read_tail_lines(path: Path, n: int, block: int = 8192) -> list[str]:
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        data = b""
        pos = size
        while pos > 0 and data.count(b"\n") <= n + 1:
            step = min(block, pos)
            pos -= step
            fh.seek(pos)
            data = fh.read(step) + data
    lines = [ln.decode("utf-8", errors="replace").rstrip("\r") for ln in data.split(b"\n")]
    lines = [ln for ln in lines if ln.strip() != ""]
    return lines[-n:]


def snapshot_tree(roots: Iterable[Path]) -> dict[str, tuple[int, int]]:
    snap: dict[str, tuple[int, int]] = {}
    for root in roots:
        for p in root.rglob("*"):
            if p.is_file():
                st = p.stat()
                snap[str(p)] = (st.st_size, st.st_mtime_ns)
    return snap


def human_size(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_ts(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, dt.datetime):
        s = x.isoformat(sep=" ")
        return s
    return str(x)


# Files read outside the source roots (evidence): stat recorded before first read
EVIDENCE_STAT: dict[str, tuple[int, int]] = {}


def track(path: Path) -> Path:
    if path.is_file() and str(path) not in EVIDENCE_STAT:
        st = path.stat()
        EVIDENCE_STAT[str(path)] = (st.st_size, st.st_mtime_ns)
    return path


def code_evidence(path: Path, pattern: str, max_hits: int = 4) -> list[str]:
    """Return matching lines (read-only) from a downloader/importer source file."""
    if not path.is_file():
        return []
    track(path)
    rx = re.compile(pattern, re.IGNORECASE)
    hits: list[str] = []
    with path.open("rb") as fh:
        for i, raw in enumerate(fh, start=1):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if rx.search(line):
                hits.append(f"`{path.name}:{i}`: {line.strip()[:160]}")
                if len(hits) >= max_hits:
                    break
    return hits


# --------------------------------------------------------------------------------------
# Group definitions
# --------------------------------------------------------------------------------------
@dataclass
class GroupDef:
    gid: str
    title: str
    root: Path
    patterns: list[str]
    kind: str  # qp_parquet | stooq | ms_csv | ts_export | reference
    session: str  # us_daily | us_intraday | crypto | crypto_daily | iran_daily | futures | none
    asset_class: str
    source: str
    source_evidence: list[str]
    symbol_of: Callable[[Path], str]
    norm: Callable[[str], str]
    priority: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def norm_equity(s: str) -> str:
    return re.sub(r"[.\-/_ ]", "", s.upper())


def norm_crypto(s: str) -> str:
    return re.sub(r"[.\-/_ ]", "", s.upper())


def stooq_symbol(p: Path) -> str:
    name = p.name
    if name.lower().endswith(".us.txt"):
        name = name[: -len(".us.txt")]
    return name.upper()


def ms_symbol(prefix: str) -> Callable[[Path], str]:
    def f(p: Path) -> str:
        return p.stem[len(prefix) :]

    return f


def ts_export_symbol(p: Path) -> str:
    parts = p.stem.split(",")
    return parts[1].strip() if len(parts) >= 2 else p.stem


def build_groups(qp: Path, ms: Path, me: Path) -> list[GroupDef]:
    qpcode = qp.parent
    mscode = ms.parent.parent
    return [
        GroupDef(
            gid="QP-US-EQ-1D",
            title="QuantPlatform · US equities · daily parquet",
            root=qp / "us_equity",
            patterns=["*/1d.parquet"],
            kind="qp_parquet",
            session="us_daily",
            asset_class="US equity / ETF",
            source="Alpaca (free IEX feed) via QuantPlatform downloader",
            source_evidence=[
                "Canonical schema `ts(UTC) | symbol | open | high | low | close | volume` = QuantPlatform's own normalised layout (one folder per ticker, `1d.parquet`/`1h.parquet`).",
                *code_evidence(
                    qpcode / "src" / "qp" / "adapters" / "alpaca.py", r"feed|adjustment: str|IEX"
                ),
            ],
            symbol_of=lambda p: p.parent.name,
            norm=norm_equity,
            priority=[
                "AAPL",
                "TSLA",
                "NVDA",
                "AMZN",
                "GOOGL",
                "WMT",
                "CMG",
                "AVGO",
                "SMCI",
                *CROSS_TICKERS,
            ],
        ),
        GroupDef(
            gid="QP-US-EQ-1H",
            title="QuantPlatform · US equities · hourly parquet",
            root=qp / "us_equity",
            patterns=["*/1h.parquet"],
            kind="qp_parquet",
            session="us_intraday",
            asset_class="US equity / ETF",
            source="Alpaca (free IEX feed) via QuantPlatform downloader",
            source_evidence=[
                "Same folder layout and schema as QP-US-EQ-1D.",
                *code_evidence(
                    qpcode / "src" / "qp" / "adapters" / "alpaca.py", r"feed|session\"|IEX"
                ),
            ],
            symbol_of=lambda p: p.parent.name,
            norm=norm_equity,
            priority=[
                "AAPL",
                "TSLA",
                "NVDA",
                "AMZN",
                "GOOGL",
                "WMT",
                "CMG",
                "AVGO",
                "SMCI",
                *CROSS_TICKERS,
            ],
        ),
        GroupDef(
            gid="QP-CRYPTO-1H",
            title="QuantPlatform · crypto · hourly parquet",
            root=qp / "crypto",
            patterns=["*/1h.parquet"],
            kind="qp_parquet",
            session="crypto",
            asset_class="crypto (spot)",
            source="ccxt public exchange (binanceus by default; fallback kraken/kucoin/bitstamp)",
            source_evidence=[
                "Folder names are ccxt pairs without slash (`BTCUSDT`, `BTCUSD`, `PAXGUSDT`).",
                *code_evidence(
                    qpcode / "src" / "qp" / "adapters" / "crypto.py",
                    r"\"binanceus\"|\"kraken\"|\"kucoin\"|\"bitstamp\"",
                ),
                *code_evidence(
                    qpcode / "scripts" / "select_and_pull_crypto.py", r"default=\"binanceus\""
                ),
            ],
            symbol_of=lambda p: p.parent.name,
            norm=norm_crypto,
            priority=["BTCUSDT", "BTCUSD", "ETHUSDT", "ETHUSD", "PAXGUSDT"],
        ),
        GroupDef(
            gid="QP-STOOQ-1H",
            title="QuantPlatform · Stooq bulk export · US stocks/ETFs · txt",
            root=qp / "us",
            patterns=["**/*.txt"],
            kind="stooq",
            session="us_intraday",
            asset_class="US equity / ETF (NASDAQ, NYSE, NYSE MKT)",
            source="Stooq (stooq.com bulk download)",
            source_evidence=[
                "Header `<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>` and tickers like `A.US` are Stooq's ASCII export format; folder names `nasdaq stocks/1`, `nyse etfs/2` match Stooq's bulk-zip layout.",
                *code_evidence(
                    qpcode / "src" / "qp" / "data" / "import_stooq.py",
                    r"Stooq is a|Central-European|Europe/Warsaw",
                ),
            ],
            symbol_of=stooq_symbol,
            norm=norm_equity,
            priority=[
                "AAPL",
                "TSLA",
                "NVDA",
                "AMZN",
                "GOOGL",
                "WMT",
                "CMG",
                "AVGO",
                "SMCI",
                *CROSS_TICKERS,
            ],
        ),
        GroupDef(
            gid="QP-REF",
            title="QuantPlatform · reference tables (assets, market cap)",
            root=qp / "reference",
            patterns=["**/*.parquet", "**/*.csv"],
            kind="reference",
            session="none",
            asset_class="reference data (not prices)",
            source="Alpaca assets endpoint (asset list) / market-cap snapshot (see downloader)",
            source_evidence=[
                *code_evidence(
                    qpcode / "scripts" / "pull_us_marketcap.py", r"nasdaq|api|url|source", 3
                ),
            ],
            symbol_of=lambda p: p.stem,
            norm=lambda s: s,
        ),
        GroupDef(
            gid="MS-US-1D",
            title="MarketScanner · US equities · daily csv (`us_<TICKER>.csv`)",
            root=ms,
            patterns=["us_*.csv"],
            kind="ms_csv",
            session="us_daily",
            asset_class="US equity / ETF (S&P 500 point-in-time members + small/mid caps)",
            source="Alpaca SIP (consolidated tape), adjustment=all",
            source_evidence=[
                "MarketScanner candle layout `date,open,high,low,close,volume` (date only).",
                *code_evidence(mscode / "scripts" / "host_download.py", r"feed=DataFeed\.SIP", 2),
                *code_evidence(
                    mscode / "scripts" / "host_download_us_pit.py", r"SIP tape keeps", 1
                ),
                *code_evidence(ms.parent / "download_sip.log", r"\[alpaca\] fetching", 1),
            ],
            symbol_of=ms_symbol("us_"),
            norm=norm_equity,
            priority=[
                "AAPL",
                "TSLA",
                "NVDA",
                "AMZN",
                "GOOGL",
                "WMT",
                "CMG",
                "AVGO",
                "SMCI",
                *CROSS_TICKERS,
            ],
        ),
        GroupDef(
            gid="MS-CRYPTO-1D",
            title="MarketScanner · crypto top-100 · daily csv (`crypto_<BASE>_<QUOTE>.csv`, `gold_PAXG_USDT.csv`)",
            root=ms,
            patterns=["crypto_*.csv", "gold_*.csv"],
            kind="ms_csv",
            session="crypto_daily",
            asset_class="crypto (spot); PAXG = gold-backed token",
            source="Binance spot via ccxt (`ccxt_binance` in manifest)",
            source_evidence=[
                *code_evidence(ms.parent / "download.log", r"Binance", 1),
            ],
            symbol_of=lambda p: p.stem.split("_", 1)[1],
            norm=norm_crypto,
            priority=["BTC_USDT", "ETH_USDT", "PAXG_USDT"],
        ),
        GroupDef(
            gid="MS-PIT-CRYPTO-1D",
            title="MarketScanner · crypto point-in-time universe (incl. delisted) · daily csv (`pit_<BASE>_<QUOTE>.csv`)",
            root=ms,
            patterns=["pit_*.csv"],
            kind="ms_csv",
            session="crypto_daily",
            asset_class="crypto (spot), includes delisted pairs",
            source="Binance spot via ccxt (point-in-time universe incl. delisted)",
            source_evidence=[
                *code_evidence(
                    ms.parent / "pit_download.log", r"\[pit\] \d+ USDT spot|delisted\]", 2
                ),
            ],
            symbol_of=ms_symbol("pit_"),
            norm=norm_crypto,
            priority=["BTC_USDT", "ETH_USDT"],
        ),
        GroupDef(
            gid="MS-IRAN-1D",
            title="MarketScanner · Tehran Stock Exchange / Farabourse · daily csv (`iran_<insCode>.csv`)",
            root=ms,
            patterns=["iran_*.csv"],
            kind="ms_csv",
            session="iran_daily",
            asset_class="Iranian equities, funds, sukuk/bonds (TSETMC instruments)",
            source="TSETMC via pytse (MarketScanner pytse adapter)",
            source_evidence=[
                "File names are TSETMC instrument codes (`insCode`, 15–17 digits); `iran_meta.csv` maps them to Persian tickers.",
                *code_evidence(
                    mscode / "backend" / "app" / "adapters" / "pytse_adapter.py", r"tsetmc|pytse", 2
                ),
            ],
            symbol_of=ms_symbol("iran_"),
            norm=lambda s: s,
        ),
        GroupDef(
            gid="ME-FUT-15M",
            title="MarketEdge · US futures continuous contracts · 15-min txt (`Data Export,@SYM, 15min.txt`)",
            root=me,
            patterns=["*.txt"],
            kind="ts_export",
            session="futures",
            asset_class="futures (equity index, rates, FX, energy, metals, ags, softs, VIX, crypto)",
            source="TradeStation (or MultiCharts) chart export via 'Data Exporter v3.0' indicator",
            source_evidence=[
                "`@` prefix continuous symbols (`@ES`, `@CL`, `@ES.D`) are TradeStation's continuous-contract convention; header fields `$/Big Point`, `S.Start`, `S.End`, `#Ticks/Point` are TradeStation/EasyLanguage terms.",
                *code_evidence(
                    me.parent.parent / "phase3" / "data" / "futures.py",
                    r"back-adjusted|back_adjusted",
                    2,
                ),
            ],
            symbol_of=ts_export_symbol,
            norm=lambda s: s.upper(),
            priority=["@ES", "@NQ", "@CL", "@GC", "@ES.D", "@VX", "@BTC", "@TY", "@EC", "@C"],
        ),
    ]


# --------------------------------------------------------------------------------------
# Loaders -> canonical frame: ts (Datetime), open, high, low, close, volume
# --------------------------------------------------------------------------------------
@dataclass
class Loaded:
    df: pl.DataFrame
    ts_kind: str  # utc | warsaw_naive | date | exchange_naive
    sampled: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


OHLCV = ["open", "high", "low", "close", "volume"]


def load_qp_parquet(p: Path) -> Loaded:
    df = pl.read_parquet(p, columns=["ts", *OHLCV])
    return Loaded(df.sort("ts"), "utc")


def load_stooq(p: Path) -> Loaded:
    sampled = p.stat().st_size > BIG_CSV_BYTES
    raw = pl.read_csv(
        p,
        infer_schema_length=0,
        n_rows=BIG_CSV_SAMPLE_LINES if sampled else None,
    )
    raw.columns = [c.strip("<>").lower() for c in raw.columns]
    df = raw.select(
        pl.concat_str([pl.col("date"), pl.col("time").str.zfill(6)], separator=" ")
        .str.strptime(pl.Datetime("us"), "%Y%m%d %H%M%S", strict=False)
        .alias("ts"),
        *[pl.col(c).cast(pl.Float64).alias(c) for c in ["open", "high", "low", "close"]],
        pl.col("vol").cast(pl.Float64).alias("volume"),
    )
    per = raw["per"].value_counts().sort("count", descending=True)
    return Loaded(
        df.sort("ts"),
        "warsaw_naive",
        sampled,
        {"per_values": {str(r[0]): int(r[1]) for r in per.iter_rows()}},
    )


def load_ms_csv(p: Path) -> Loaded:
    sampled = p.stat().st_size > BIG_CSV_BYTES
    df = pl.read_csv(p, n_rows=BIG_CSV_SAMPLE_LINES if sampled else None, infer_schema_length=10000)
    df = df.select(
        pl.col("date")
        .cast(pl.Utf8)
        .str.strptime(pl.Date, "%Y-%m-%d")
        .cast(pl.Datetime("us"))
        .alias("ts"),
        *[pl.col(c).cast(pl.Float64) for c in OHLCV],
    )
    return Loaded(df.sort("ts"), "date", sampled)


def ts_export_header(p: Path) -> tuple[int, dict[str, Any]]:
    lines = read_head_lines(p, 20)
    meta: dict[str, Any] = {"exporter": lines[0].strip() if lines else ""}
    hdr_idx = -1
    for i, ln in enumerate(lines):
        if " = " in ln and "description" not in meta:
            meta["description"] = ln.split(" = ", 1)[1].strip()
            m = re.search(r"\[([A-Za-z]{3}\d{2})\]", ln)
            meta["contract_tag"] = m.group(1) if m else None
        if ln.startswith("Symbol,TimeFrame"):
            keys = [k.strip() for k in ln.split(",")]
            vals = [v.strip() for v in lines[i + 1].split(",")]
            meta["meta"] = dict(zip(keys, vals, strict=False))
        if ln.startswith("Date,Time"):
            hdr_idx = i
            break
    return hdr_idx, meta


def load_ts_export(p: Path) -> Loaded:
    hdr_idx, meta = ts_export_header(p)
    df = pl.read_csv(p, skip_rows=hdr_idx, infer_schema_length=0)
    df = df.select(
        pl.concat_str([pl.col("Date"), pl.col("Time")], separator=" ")
        .str.strptime(pl.Datetime("us"), "%m/%d/%Y %H:%M")
        .alias("ts"),
        *[pl.col(c.capitalize()).cast(pl.Float64).alias(c) for c in OHLCV],
    )
    return Loaded(
        df.sort("ts"), "exchange_naive", False, {"header": meta, "header_line_index": hdr_idx}
    )


LOADERS: dict[str, Callable[[Path], Loaded]] = {
    "qp_parquet": load_qp_parquet,
    "stooq": load_stooq,
    "ms_csv": load_ms_csv,
    "ts_export": load_ts_export,
}


# --------------------------------------------------------------------------------------
# Light pass (every file): size, symbol, first/last timestamp
# --------------------------------------------------------------------------------------
def light_info(g: GroupDef, p: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"path": str(p), "symbol": g.symbol_of(p), "bytes": p.stat().st_size}
    if g.kind == "qp_parquet":
        r = (
            pl.scan_parquet(p)
            .select(
                pl.col("ts").min().alias("first"),
                pl.col("ts").max().alias("last"),
                pl.len().alias("rows"),
            )
            .collect()
        )
        info.update(first=r["first"][0], last=r["last"][0], rows=int(r["rows"][0]))
        if g.session == "us_daily":
            tod = (
                pl.scan_parquet(p)
                .select(pl.col("ts").dt.strftime("%H:%M").unique().sort())
                .collect()
            )
            info["tod_labels"] = ",".join(tod["ts"].to_list())
    elif g.kind == "stooq":
        head = read_head_lines(p, 2)
        tail = read_tail_lines(p, 1)
        if len(head) >= 2 and tail:
            a, b = head[1].split(","), tail[0].split(",")
            info.update(
                first=dt.datetime.strptime(a[2] + a[3].zfill(6), "%Y%m%d%H%M%S"),
                last=dt.datetime.strptime(b[2] + b[3].zfill(6), "%Y%m%d%H%M%S"),
                per=a[1],
            )
    elif g.kind == "ms_csv":
        head = read_head_lines(p, 2)
        tail = read_tail_lines(p, 1)
        if len(head) >= 2 and tail and tail[0] != head[0]:
            info.update(
                first=dt.datetime.strptime(head[1].split(",")[0], "%Y-%m-%d"),
                last=dt.datetime.strptime(tail[0].split(",")[0], "%Y-%m-%d"),
            )
    elif g.kind == "ts_export":
        idx, meta = ts_export_header(p)
        head = read_head_lines(p, idx + 2)
        tail = read_tail_lines(p, 1)
        a, b = head[idx + 1].split(","), tail[0].split(",")
        info.update(
            first=dt.datetime.strptime(a[0] + " " + a[1], "%m/%d/%Y %H:%M"),
            last=dt.datetime.strptime(b[0] + " " + b[1], "%m/%d/%Y %H:%M"),
            header=meta,
        )
    return info


# --------------------------------------------------------------------------------------
# Deep analysis helpers
# --------------------------------------------------------------------------------------
def tf_label(minutes: float) -> str:
    table = {1: "1m", 5: "5m", 15: "15m", 30: "30m", 60: "1h", 240: "4h", 1440: "1d", 10080: "1w"}
    m = round(minutes)
    return table.get(m, f"{minutes:g}min")


def to_utc(df: pl.DataFrame, ts_kind: str) -> pl.Series | None:
    if ts_kind == "utc":
        return df["ts"]
    if ts_kind == "warsaw_naive":
        return (
            df["ts"]
            .dt.replace_time_zone(WARSAW, ambiguous="earliest", non_existent="null")
            .dt.convert_time_zone(UTC)
        )
    return None


def weekday_counts(ts: pl.Series) -> dict[str, int]:
    names = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
    vc = ts.dt.weekday().alias("wd").value_counts().sort("wd")
    return {names[int(r[0])]: int(r[1]) for r in vc.iter_rows()}


def label_counts(ts: pl.Series, top: int = 40) -> dict[str, int]:
    vc = ts.dt.strftime("%H:%M").value_counts().sort("ts")
    return {str(r[0]): int(r[1]) for r in vc.head(top).iter_rows()}


def first_last_labels(ts: pl.Series, day: pl.Series) -> tuple[Counter[str], Counter[str]]:
    d = pl.DataFrame({"ts": ts, "day": day})
    agg = d.group_by("day", maintain_order=True).agg(
        pl.col("ts").min().alias("f"), pl.col("ts").max().alias("l")
    )
    return Counter(agg["f"].dt.strftime("%H:%M").to_list()), Counter(
        agg["l"].dt.strftime("%H:%M").to_list()
    )


def us_dst_windows(years: Iterable[int]) -> list[tuple[dt.date, dt.date]]:
    """Date windows where US and EU DST disagree (US on, EU off)."""
    out = []
    for y in years:
        # US: 2nd Sunday March -> 1st Sunday Nov ; EU: last Sunday March -> last Sunday Oct
        mar1 = dt.date(y, 3, 1)
        us_start = mar1 + dt.timedelta(days=(6 - mar1.weekday()) % 7 + 7)
        nov1 = dt.date(y, 11, 1)
        us_end = nov1 + dt.timedelta(days=(6 - nov1.weekday()) % 7)
        mar31 = dt.date(y, 3, 31)
        eu_start = mar31 - dt.timedelta(days=(mar31.weekday() + 1) % 7)
        oct31 = dt.date(y, 10, 31)
        eu_end = oct31 - dt.timedelta(days=(oct31.weekday() + 1) % 7)
        out.append((us_start, eu_start))
        out.append((eu_end, us_end))
    return out


def in_windows(d: dt.date, wins: list[tuple[dt.date, dt.date]]) -> bool:
    return any(a <= d < b for a, b in wins)


def busday_gaps(dates: np.ndarray, weekmask: str) -> int:
    if len(dates) < 2:
        return 0
    bd = np.busday_count(dates[:-1], dates[1:], weekmask=weekmask)
    return int((bd > GAP_MULTIPLE).sum())


def hhmm_to_min(s: str) -> int:
    s = s.zfill(4)
    return int(s[:2]) * 60 + int(s[2:])


def basic_stats(df: pl.DataFrame) -> dict[str, Any]:
    n = df.height
    out: dict[str, Any] = {"rows": n}
    if n == 0:
        return out
    ts = df["ts"]
    diffs = ts.diff().drop_nulls().dt.total_minutes()
    pos = diffs.filter(diffs > 0)
    med = float(pos.median()) if pos.len() else float("nan")
    mode = float(pos.mode().min()) if pos.len() else float("nan")  # type: ignore[arg-type]
    out.update(
        mode_diff_min=mode,
        first=ts.min(),
        last=ts.max(),
        median_diff_min=med,
        share_diffs_eq_median=float((pos == med).mean()) if pos.len() else float("nan"),
        non_monotonic=int((diffs < 0).sum()),
        dup_ts=int(n - ts.n_unique()),
        high_lt_low=int((df["high"] < df["low"]).sum()),
        ohlc_outside_range=int(
            (
                (df["open"] > df["high"])
                | (df["open"] < df["low"])
                | (df["close"] > df["high"])
                | (df["close"] < df["low"])
            ).sum()
        ),
        nonpos_price=int(
            ((df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)).sum()
        ),
        null_cells=int(sum(df[c].null_count() for c in df.columns)),
        zero_volume_share=float((df["volume"] == 0).mean()),
        min_low=float(df["low"].min()),  # type: ignore[arg-type]
        max_high=float(df["high"].max()),  # type: ignore[arg-type]
    )
    rets = (df["close"] / df["close"].shift(1) - 1).drop_nulls()
    out["big_moves"] = int((rets.abs() > BIG_MOVE).sum())
    return out


# --------------------------------------------------------------------------------------
# Session / timezone analyses per group kind
# --------------------------------------------------------------------------------------
def analyse_us_intraday(ld: Loaded, tf_min: float) -> dict[str, Any]:
    df = ld.df
    utc = to_utc(df, ld.ts_kind)
    assert utc is not None
    ny = utc.dt.convert_time_zone(NY)
    ny_day = ny.dt.date()
    res: dict[str, Any] = {}
    f_ny, l_ny = first_last_labels(ny, ny_day)
    res["ny_first_label_per_day"] = dict(f_ny.most_common(6))
    res["ny_last_label_per_day"] = dict(l_ny.most_common(6))
    res["ny_label_counts"] = label_counts(ny)
    # literal UTC session probe requested by the task
    utc_min = utc.dt.hour().cast(pl.Int32) * 60 + utc.dt.minute().cast(pl.Int32)
    res["bars_utc_0800_1330"] = int(((utc_min >= 8 * 60) & (utc_min < 13 * 60 + 30)).sum())
    res["bars_utc_ge_2000"] = int((utc_min >= 20 * 60).sum())
    # ET-local probe: bars starting before 09:00 ET or at/after 16:00 ET
    ny_min = ny.dt.hour().cast(pl.Int32) * 60 + ny.dt.minute().cast(pl.Int32)
    res["bars_ny_before_0900"] = int((ny_min < 9 * 60).sum())
    res["bars_ny_at_or_after_1600"] = int((ny_min >= 16 * 60).sum())
    res["bars_ny_at_or_after_1700"] = int((ny_min >= 17 * 60).sum())
    # volume share of bars whose hour lies outside the 09:00-15:00 ET labels (extended hours
    # for hour-aligned bar-start data)
    vol = df["volume"]
    ext = (ny_min < 9 * 60) | (ny_min >= 16 * 60)
    res["volume_total"] = float(vol.sum())
    res["volume_ext_labels"] = float(vol.filter(ext).sum())
    # UTC first label by NY DST state
    summer = ny.dt.dst_offset().dt.total_minutes() > 0
    d = pl.DataFrame({"utc": utc, "day": ny_day, "summer": summer})
    agg = d.group_by("day", maintain_order=True).agg(
        pl.col("utc").min().alias("f"), pl.col("summer").first()
    )
    res["utc_first_label_summer"] = dict(
        Counter(agg.filter(pl.col("summer"))["f"].dt.strftime("%H:%M").to_list()).most_common(4)
    )
    res["utc_first_label_winter"] = dict(
        Counter(agg.filter(~pl.col("summer"))["f"].dt.strftime("%H:%M").to_list()).most_common(4)
    )
    # raw local labels (Stooq: Warsaw wall clock) inside / outside US-EU DST mismatch windows
    if ld.ts_kind == "warsaw_naive":
        raw = df["ts"]
        rday = raw.dt.date()
        wins = us_dst_windows(range(raw.min().year, raw.max().year + 1))  # type: ignore[union-attr]
        dd = (
            pl.DataFrame({"ts": raw, "day": rday})
            .group_by("day", maintain_order=True)
            .agg(pl.col("ts").min().alias("f"), pl.col("ts").max().alias("l"))
        )
        mism = [in_windows(x, wins) for x in dd["day"].to_list()]
        dd = dd.with_columns(pl.Series("mismatch", mism))
        for flag, name in [(False, "normal"), (True, "us_eu_dst_mismatch")]:
            sub = dd.filter(pl.col("mismatch") == flag)
            res[f"raw_first_label_{name}"] = dict(
                Counter(sub["f"].dt.strftime("%H:%M").to_list()).most_common(4)
            )
            res[f"raw_last_label_{name}"] = dict(
                Counter(sub["l"].dt.strftime("%H:%M").to_list()).most_common(4)
            )
            res[f"days_{name}"] = sub.height
        res["raw_label_counts"] = label_counts(raw)
        res["nonexistent_local_times"] = int(utc.null_count())
    # quality: intraday gaps inside a NY day, and missing trading days
    dfq = pl.DataFrame({"ny": ny, "day": ny_day}).drop_nulls()
    g = dfq.with_columns(
        (pl.col("ny").diff().dt.total_minutes()).alias("d"),
        (pl.col("day") == pl.col("day").shift(1)).alias("same"),
    )
    res["intraday_gaps"] = int(
        g.filter(pl.col("same") & (pl.col("d") > GAP_MULTIPLE * tf_min)).height
    )
    days = np.array(sorted(set(ny_day.drop_nulls().to_list())), dtype="datetime64[D]")
    res["missing_day_gaps"] = busday_gaps(days, "1111100")
    res["bars_per_day"] = dict(
        Counter(dfq.group_by("day", maintain_order=True).len()["len"].to_list()).most_common(5)
    )
    # half days
    half = {}
    for h in US_HALF_DAYS:
        sub = dfq.filter(pl.col("day") == h)
        if sub.height:
            half[str(h)] = f"{sub.height} bars, last label {sub['ny'].max().strftime('%H:%M')} ET"  # type: ignore[union-attr]
    res["half_days"] = half
    day_set = set(ny_day.drop_nulls().to_list())
    hol = [str(h) for h in US_HOLIDAYS if h in day_set]
    res["bars_on_holidays"] = hol
    return res


def analyse_daily(ld: Loaded, session: str) -> dict[str, Any]:
    ts = ld.df["ts"]
    res: dict[str, Any] = {"weekday_counts": weekday_counts(ts)}
    days = np.array(ts.dt.date().to_list(), dtype="datetime64[D]")
    if session == "us_daily":
        res["missing_day_gaps"] = busday_gaps(days, "1111100")
        dset = set(ts.dt.date().to_list())
        res["rows_on_nyse_holidays"] = [str(h) for h in US_HOLIDAYS if h in dset]
        res["holidays_in_range"] = [
            str(h) for h in US_HOLIDAYS if ts.min().date() <= h <= ts.max().date()
        ]  # type: ignore[union-attr]
        if ld.ts_kind == "utc":
            res["time_of_day_labels"] = label_counts(ts)
    elif session == "iran_daily":
        res["missing_day_gaps"] = busday_gaps(days, "1110011")  # Sat-Wed trading week
    elif session == "crypto_daily":
        if len(days) > 1:
            cal = np.diff(days).astype(int)
            res["missing_day_gaps"] = int((cal > GAP_MULTIPLE).sum())
    return res


def analyse_crypto_intraday(ld: Loaded, tf_min: float) -> dict[str, Any]:
    ts = ld.df["ts"]
    diffs = ts.diff().drop_nulls().dt.total_minutes()
    return {
        "weekday_counts": weekday_counts(ts),
        "distinct_hours": int(ts.dt.hour().n_unique()),
        "minute_labels": dict(Counter(ts.dt.minute().to_list()).most_common(3)),
        "gaps_gt_3tf": int((diffs > GAP_MULTIPLE * tf_min).sum()),
        "largest_gap_hours": float(diffs.max() / 60) if diffs.len() else 0.0,  # type: ignore[operator]
    }


def analyse_futures(ld: Loaded, tf_min: float) -> dict[str, Any]:
    df = ld.df
    meta = ld.extra.get("header", {}).get("meta", {})
    s_start = meta.get("S.Start")
    s_end = meta.get("S.End")
    tick = float(meta.get("Tick Size", "nan") or "nan")
    ts = df["ts"]
    res: dict[str, Any] = {"header": ld.extra.get("header"), "weekday_counts": weekday_counts(ts)}
    labels = ts.dt.strftime("%H%M")
    lab_set = Counter(labels.to_list())
    if s_start and s_end:
        ss, se = s_start.zfill(4), s_end.zfill(4)
        res["label_eq_session_start"] = lab_set.get(ss, 0)
        res["label_eq_session_end"] = lab_set.get(se, 0)
        first_after = (
            dt.datetime(2000, 1, 1) + dt.timedelta(minutes=hhmm_to_min(ss) + tf_min)
        ).strftime("%H%M")
        res["label_eq_session_start_plus_tf"] = lab_set.get(first_after, 0)
    # first label of each session (bar after a gap > 30 min), by season
    d = pl.DataFrame({"ts": ts}).with_columns(pl.col("ts").diff().dt.total_minutes().alias("gap"))
    starts = d.filter((pl.col("gap") > 30) | pl.col("gap").is_null())
    month = starts["ts"].dt.month()
    winter = starts.filter(month.is_in([12, 1, 2]))
    summer = starts.filter(month.is_in([6, 7, 8]))
    res["session_first_label_winter"] = dict(
        Counter(winter["ts"].dt.strftime("%a %H:%M").to_list()).most_common(4)
    )
    res["session_first_label_summer"] = dict(
        Counter(summer["ts"].dt.strftime("%a %H:%M").to_list()).most_common(4)
    )
    # gaps
    gaps = d.filter(pl.col("gap") > GAP_MULTIPLE * tf_min).with_columns(
        (pl.col("ts") - pl.duration(minutes=pl.col("gap"))).alias("prev")
    )
    prev_lab = gaps["prev"].dt.strftime("%H%M")
    prev_wd = gaps["prev"].dt.weekday()
    expected = (prev_lab == (s_end or "").zfill(4)) | (prev_wd >= 5)
    res["gaps_gt_3tf_total"] = gaps.height
    res["gaps_gt_3tf_excl_session_break_weekend"] = int((~expected).sum())
    res["gaps_gt_1day_weekday"] = int(((gaps["gap"] > 24 * 60) & (prev_wd <= 4)).sum())
    # adjustment evidence
    res["negative_or_zero_prices"] = int((df["low"] <= 0).sum())
    if not math.isnan(tick) and tick > 0:
        n = df.height
        early = df.head(min(n, 20000))
        late = df.tail(min(n, 20000))

        def on_grid(x: pl.Series) -> float:
            q = x / tick
            return float(((q - q.round(0)).abs() < 1e-6).mean())

        res["tick_grid_share_first20k_close"] = on_grid(early["close"])
        res["tick_grid_share_last20k_close"] = on_grid(late["close"])
    # largest bar-to-bar jumps (open vs previous close) -- roll evidence
    j = df.with_columns(
        (pl.col("open") - pl.col("close").shift(1)).alias("jump"),
        pl.col("ts").diff().dt.total_minutes().alias("gap"),
    )
    j = j.with_columns((pl.col("high") - pl.col("low")).rolling_median(96).shift(1).alias("rng"))
    j = j.filter(pl.col("rng") > 0).with_columns(
        (pl.col("jump").abs() / pl.col("rng")).alias("jump_x_range")
    )
    top = j.sort("jump_x_range", descending=True).head(20)
    qroll = [(t.month in (3, 6, 9, 12) and 5 <= t.day <= 16) for t in top["ts"].to_list()]
    res["top_jumps"] = [
        {
            "ts": fmt_ts(r["ts"]),
            "jump": round(r["jump"], 6),
            "x_median_range": round(r["jump_x_range"], 1),
            "gap_min": r["gap"],
        }
        for r in top.head(8).iter_rows(named=True)
    ]
    res["top20_jumps_in_quarterly_roll_window_share"] = (
        float(np.mean(qroll)) if qroll else float("nan")
    )
    return res


# --------------------------------------------------------------------------------------
# Daily bar extraction for cross-source checks
# --------------------------------------------------------------------------------------
def daily_bars(ld: Loaded, kind: str, session: str) -> pl.DataFrame:
    df = ld.df
    if session in ("us_daily", "crypto_daily", "iran_daily"):
        return df.select(pl.col("ts").dt.date().alias("date"), "open", "close", "volume")
    if session == "us_intraday":
        utc = to_utc(df, ld.ts_kind)
        day = utc.dt.convert_time_zone(NY).dt.date()  # type: ignore[union-attr]
    else:  # crypto intraday: UTC day
        day = df["ts"].dt.date()
    return (
        df.with_columns(day.alias("date"))
        .drop_nulls("date")
        .group_by("date", maintain_order=True)
        .agg(pl.col("open").first(), pl.col("close").last(), pl.col("volume").sum())
        .sort("date")
    )


def split_check(bars: pl.DataFrame, when: dt.date) -> dict[str, Any] | None:
    before = bars.filter(pl.col("date") < when).tail(1)
    after = bars.filter(pl.col("date") >= when).head(1)
    if before.height == 0 or after.height == 0:
        return None
    if (after["date"][0] - before["date"][0]).days > 5:
        return None
    pc, op = float(before["close"][0]), float(after["open"][0])
    return {
        "prev_date": str(before["date"][0]),
        "prev_close": pc,
        "date": str(after["date"][0]),
        "open": op,
        "ratio_prev_close_to_open": round(pc / op, 3),
    }


# --------------------------------------------------------------------------------------
# Group processing
# --------------------------------------------------------------------------------------
def list_files(g: GroupDef) -> list[Path]:
    files: set[Path] = set()
    if not g.root.exists():
        return []
    for pat in g.patterns:
        files.update(p for p in g.root.glob(pat) if p.is_file())
    return sorted(files, key=lambda p: str(p).lower())


def choose_sample(g: GroupDef, files: list[Path]) -> list[Path]:
    by_sym: dict[str, Path] = {}
    for p in files:
        by_sym.setdefault(g.norm(g.symbol_of(p)), p)
    chosen: list[Path] = []
    for s in g.priority:
        p = by_sym.get(g.norm(s))
        if p is not None and p not in chosen:
            chosen.append(p)
    rest = [p for p in files if p not in chosen]
    k = max(0, MAX_DEEP_FILES - len(chosen))
    if rest and k:
        step = len(rest) / min(k, len(rest))
        chosen.extend(rest[int(i * step)] for i in range(min(k, len(rest))))
    return chosen[:MAX_DEEP_FILES]


def raw_samples(g: GroupDef, p: Path) -> dict[str, Any]:
    if g.kind in ("qp_parquet",) or p.suffix == ".parquet":
        df = pl.read_parquet(p)
        return {
            "file": str(p),
            "note": "parquet: rows rendered from the stored values (Python repr), dtypes listed in schema",
            "head": [repr(r) for r in df.head(HEAD_ROWS).iter_rows()],
            "tail": [repr(r) for r in df.tail(TAIL_ROWS).iter_rows()],
        }
    head_n = HEAD_ROWS + 1
    if g.kind == "ts_export":
        idx, _ = ts_export_header(p)
        head_n = idx + 1 + HEAD_ROWS
    return {
        "file": str(p),
        "head": read_head_lines(p, head_n),
        "tail": read_tail_lines(p, TAIL_ROWS),
    }


def schema_of(g: GroupDef, p: Path) -> dict[str, str]:
    if p.suffix == ".parquet":
        return {k: str(v) for k, v in pl.read_parquet_schema(p).items()}
    if g.kind == "ts_export":
        idx, _ = ts_export_header(p)
        cols = read_head_lines(p, idx + 1)[idx].split(",")
        return {c: "str (text file; parsed as noted)" for c in cols}
    df = pl.read_csv(p, n_rows=1000, infer_schema_length=1000)
    return {k: str(v) for k, v in df.schema.items()}


def summarise_dates(infos: list[dict[str, Any]]) -> dict[str, Any]:
    firsts = sorted(i["first"] for i in infos if i.get("first") is not None)
    lasts = sorted(i["last"] for i in infos if i.get("last") is not None)
    if not firsts:
        return {}

    def pick(xs: list[Any]) -> dict[str, str]:
        return {"min": fmt_ts(xs[0]), "median": fmt_ts(xs[len(xs) // 2]), "max": fmt_ts(xs[-1])}

    return {"first_ts": pick(firsts), "last_ts": pick(lasts)}


def process_group(g: GroupDef, errors: list[dict[str, str]]) -> dict[str, Any]:
    t0 = time.time()
    files = list_files(g)
    out: dict[str, Any] = {
        "group_id": g.gid,
        "title": g.title,
        "root": str(g.root),
        "patterns": g.patterns,
        "file_count": len(files),
        "total_bytes": sum(p.stat().st_size for p in files),
        "extensions": dict(Counter(p.suffix.lower() for p in files)),
        "probable_source": g.source,
        "source_evidence": list(g.source_evidence),
        "asset_class_guess": g.asset_class,
        "notes": list(g.notes),
    }
    if not files:
        out["notes"].append("No files found.")
        return out
    subdirs = Counter(str(p.parent.relative_to(g.root)) for p in files)
    if len(subdirs) > 1 and g.kind != "qp_parquet":
        out["files_per_subfolder"] = dict(sorted(subdirs.items()))
    symbols = sorted({g.symbol_of(p) for p in files})
    out["symbol_count"] = len(symbols)
    out["symbols_first30"] = symbols[:30]
    out["_symbols_all"] = symbols
    out["_norm_symbols"] = sorted({g.norm(s) for s in symbols})

    if g.kind == "reference":
        out["tables"] = []
        for p in files:
            try:
                df = pl.read_parquet(p) if p.suffix == ".parquet" else pl.read_csv(p)
                out["tables"].append(
                    {
                        "file": str(p.relative_to(g.root)),
                        "rows": df.height,
                        "schema": {k: str(v) for k, v in df.schema.items()},
                        "distinct_as_of": sorted({str(x) for x in df["as_of"].unique().to_list()})
                        if "as_of" in df.columns
                        else None,
                    }
                )
            except Exception as e:
                errors.append({"group": g.gid, "file": str(p), "error": repr(e)})
        out["raw_samples"] = raw_samples(g, next(p for p in files if p.suffix == ".csv"))
        out["elapsed_s"] = round(time.time() - t0, 1)
        return out

    # ---- light pass over every file
    infos: list[dict[str, Any]] = []
    for p in files:
        try:
            infos.append(light_info(g, p))
        except Exception as e:
            errors.append({"group": g.gid, "file": str(p), "stage": "light", "error": repr(e)})
    out["light_pass_files"] = len(infos)
    out["date_range_all_files"] = summarise_dates(infos)
    if g.kind == "stooq":
        out["stooq_PER_first_row_all_files"] = dict(Counter(i.get("per") for i in infos))
    if g.kind == "ts_export":
        out["futures_headers"] = [
            {
                "symbol": i["symbol"],
                "description": i["header"].get("description"),
                "contract_tag": i["header"].get("contract_tag"),
                **{
                    k: i["header"].get("meta", {}).get(k)
                    for k in ["Exchange", "S.Start", "S.End", "$/Big Point", "Tick Size"]
                },
                "first": fmt_ts(i["first"]),
                "last": fmt_ts(i["last"]),
                "size": human_size(i["bytes"]),
            }
            for i in infos
        ]
    if len(infos) <= 120:
        out["per_symbol_range"] = [
            {
                "symbol": i["symbol"],
                "first": fmt_ts(i.get("first")),
                "last": fmt_ts(i.get("last")),
                "rows": i.get("rows"),
                "size": human_size(i["bytes"]),
            }
            for i in infos
        ]
    out["_light"] = infos
    empty = [i for i in infos if i.get("first") is None or i.get("rows") == 0]
    out["empty_files"] = len(empty)
    out["empty_file_examples"] = [
        Path(i["path"]).relative_to(g.root).as_posix() for i in empty[:15]
    ]
    if any("tod_labels" in i for i in infos):
        out["daily_ts_time_of_day_conventions_all_files"] = dict(
            Counter(i.get("tod_labels") for i in infos if i.get("tod_labels")).most_common()
        )
        conv = [(i["symbol"], i["tod_labels"]) for i in infos if i.get("tod_labels") == "00:00"]
        out["files_with_0000_utc_convention"] = [s for s, _ in conv]

    # ---- deep pass on a sample (non-empty files only)
    empty_paths = {i["path"] for i in empty}
    sample = choose_sample(g, [p for p in files if str(p) not in empty_paths])
    out["deep_sample_files"] = len(sample)
    out["deep_sample_symbols"] = [g.symbol_of(p) for p in sample]
    out["deep_sampled"] = len(sample) < len(files)
    rep = sample[0]
    out["representative_file"] = str(rep)
    try:
        out["schema"] = schema_of(g, rep)
        out["raw_samples"] = raw_samples(g, rep)
    except Exception as e:
        errors.append({"group": g.gid, "file": str(rep), "stage": "schema", "error": repr(e)})

    per_file: list[dict[str, Any]] = []
    session_res: list[dict[str, Any]] = []
    daily: dict[str, pl.DataFrame] = {}
    medians: list[float] = []
    modes: list[float] = []
    any_sampled_rows = False
    for p in sample:
        sym = g.symbol_of(p)
        try:
            ld = LOADERS[g.kind](p)
            any_sampled_rows |= ld.sampled
            st = basic_stats(ld.df)
            st["symbol"] = sym
            if ld.extra.get("per_values"):
                st["per_values"] = ld.extra["per_values"]
            med_tf = st.get("median_diff_min", float("nan"))
            if not math.isnan(med_tf):
                medians.append(med_tf)
                modes.append(st["mode_diff_min"])
            # bar grid = most frequent spacing (robust for sparse/illiquid files)
            tf = st.get("mode_diff_min", float("nan"))
            if g.session == "us_intraday":
                sres = analyse_us_intraday(ld, tf)
            elif g.session in ("us_daily", "iran_daily", "crypto_daily"):
                sres = analyse_daily(ld, g.session)
            elif g.session == "crypto":
                sres = analyse_crypto_intraday(ld, tf)
            elif g.session == "futures":
                sres = analyse_futures(ld, tf)
            else:
                sres = {}
            sres["symbol"] = sym
            session_res.append(sres)
            per_file.append(st)
            if g.norm(sym) in {
                g.norm(s)
                for s in [x[0] for x in SPLIT_PROBES]
                + CROSS_TICKERS
                + ["BTCUSDT", "BTC_USDT", "ETHUSDT", "ETH_USDT"]
            }:
                daily[g.norm(sym)] = daily_bars(ld, g.kind, g.session)
        except Exception as e:
            errors.append(
                {
                    "group": g.gid,
                    "file": str(p),
                    "stage": "deep",
                    "error": repr(e),
                    "trace": traceback.format_exc(limit=2),
                }
            )
    out["rows_sampled_from_big_files"] = any_sampled_rows
    out["per_file_stats"] = per_file
    out["session_analysis"] = session_res
    out["_daily"] = daily

    # timeframe
    if medians:
        tfs = Counter(tf_label(m) for m in medians)
        grid = Counter(tf_label(m) for m in modes)
        dominant = tfs.most_common(1)[0][0]
        out["timeframe"] = {
            "dominant": dominant,
            "files_median_eq_dominant": tfs[dominant],
            "files_median_other (sparse/illiquid: median gap > bar size)": len(medians)
            - tfs[dominant],
            "inferred_from_median_diff": dict(tfs),
            "most_frequent_spacing_per_file": dict(grid),
            "mixed": len(grid) > 1,
            "median_share_of_diffs_eq_median": round(
                statistics.median(s.get("share_diffs_eq_median", 0) for s in per_file), 3
            ),
        }
    # quality aggregate + extrapolation
    keys = [
        "rows",
        "dup_ts",
        "non_monotonic",
        "high_lt_low",
        "ohlc_outside_range",
        "nonpos_price",
        "null_cells",
        "big_moves",
    ]
    agg = {k: int(sum(s.get(k, 0) for s in per_file)) for k in keys}
    gap_key = {
        "us_intraday": "intraday_gaps",
        "us_daily": "missing_day_gaps",
        "iran_daily": "missing_day_gaps",
        "crypto_daily": "missing_day_gaps",
        "crypto": "gaps_gt_3tf",
        "futures": "gaps_gt_3tf_excl_session_break_weekend",
    }.get(g.session)
    if gap_key:
        agg["missing_bar_gaps"] = int(sum(s.get(gap_key, 0) for s in session_res))
    if g.session == "us_intraday":
        agg["missing_day_gaps"] = int(sum(s.get("missing_day_gaps", 0) for s in session_res))
    zv = [s["zero_volume_share"] for s in per_file if "zero_volume_share" in s]
    agg["zero_volume_share_median_file"] = round(statistics.median(zv), 4) if zv else None
    agg["zero_volume_share_max_file"] = round(max(zv), 4) if zv else None
    agg["files_with_any_dup_ts"] = sum(1 for s in per_file if s.get("dup_ts", 0) > 0)
    agg["files_with_big_moves"] = sum(1 for s in per_file if s.get("big_moves", 0) > 0)
    agg["files_with_nonpos_price"] = sum(1 for s in per_file if s.get("nonpos_price", 0) > 0)
    agg["files_with_high_lt_low"] = sum(1 for s in per_file if s.get("high_lt_low", 0) > 0)
    agg["files_in_sample"] = len(per_file)
    if len(per_file) and len(files) > len(per_file):
        scale = len(files) / len(per_file)
        agg["extrapolated_to_all_files"] = {
            k: round(agg[k] * scale)
            for k in [
                "rows",
                "dup_ts",
                "high_lt_low",
                "nonpos_price",
                "big_moves",
                "missing_bar_gaps",
            ]
            if k in agg
        }
    out["quality"] = agg
    out["elapsed_s"] = round(time.time() - t0, 1)
    return out


# --------------------------------------------------------------------------------------
# Cross-group checks
# --------------------------------------------------------------------------------------
def cross_checks(results: list[dict[str, Any]]) -> dict[str, Any]:
    daily = {r["group_id"]: r.get("_daily", {}) for r in results}
    out: dict[str, Any] = {
        "splits": [],
        "price_ratio_vs_ms": [],
        "volume_ratio_vs_ms": [],
        "crypto": [],
    }
    for tick, when, factor in SPLIT_PROBES:
        for gid in ["QP-US-EQ-1D", "QP-US-EQ-1H", "QP-STOOQ-1H", "MS-US-1D"]:
            bars = daily.get(gid, {}).get(norm_equity(tick))
            if bars is None:
                continue
            chk = split_check(bars, when)
            if chk is None:
                continue
            r = chk["ratio_prev_close_to_open"]
            verdict = (
                "unadjusted"
                if abs(r / factor - 1) < 0.25
                else ("adjusted" if abs(r - 1) < 0.25 else "unclear")
            )
            out["splits"].append(
                {
                    "group": gid,
                    "ticker": tick,
                    "split_date": str(when),
                    "factor": factor,
                    **chk,
                    "verdict": verdict,
                }
            )
    ref = daily.get("MS-US-1D", {})
    for gid in ["QP-US-EQ-1D", "QP-US-EQ-1H", "QP-STOOQ-1H"]:
        for tick in CROSS_TICKERS + [t for t, _, _ in SPLIT_PROBES]:
            a = daily.get(gid, {}).get(norm_equity(tick))
            b = ref.get(norm_equity(tick))
            if a is None or b is None:
                continue
            j = a.join(b, on="date", suffix="_ms").filter(pl.col("close_ms") > 0)
            if j.height < 20:
                continue
            j = j.with_columns(
                (pl.col("close") / pl.col("close_ms")).alias("pr"),
                (pl.col("volume") / pl.col("volume_ms")).alias("vr"),
                pl.col("date").dt.year().alias("y"),
            )
            by_y = (
                j.group_by("y", maintain_order=True)
                .agg(pl.col("pr").median(), pl.col("vr").median(), pl.len())
                .sort("y")
            )
            key = (gid, tick)
            if any(x == key for x in [(d["group"], d["ticker"]) for d in out["price_ratio_vs_ms"]]):
                continue
            out["price_ratio_vs_ms"].append(
                {
                    "group": gid,
                    "ticker": tick,
                    "common_days": j.height,
                    "median_close_ratio_by_year": {
                        int(r[0]): round(float(r[1]), 4) for r in by_y.iter_rows()
                    },
                    "median_volume_ratio_by_year": {
                        int(r[0]): round(float(r[2]), 4) for r in by_y.iter_rows()
                    },
                }
            )
    # crypto: QP BTCUSDT (binanceus hourly -> UTC day) vs MS BTC_USDT (binance daily)
    for qa, mb in [("BTCUSDT", "BTCUSDT"), ("ETHUSDT", "ETHUSDT")]:
        a = daily.get("QP-CRYPTO-1H", {}).get(qa)
        b = daily.get("MS-CRYPTO-1D", {}).get(mb)
        if a is None or b is None:
            continue
        j = a.join(b, on="date", suffix="_ms")
        j = j.with_columns(
            (pl.col("close") / pl.col("close_ms")).alias("pr"),
            (pl.col("volume") / pl.col("volume_ms")).alias("vr"),
        )
        out["crypto"].append(
            {
                "pair": qa,
                "common_days": j.height,
                "median_close_ratio_QP_over_MS": round(float(j["pr"].median()), 5),  # type: ignore[arg-type]
                "p99_abs_close_ratio_dev": round(float((j["pr"] - 1).abs().quantile(0.99)), 5),  # type: ignore[arg-type]
                "median_volume_ratio_QP_over_MS": round(float(j["vr"].median()), 5),  # type: ignore[arg-type]
            }
        )
    return out


def overlaps(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    price_groups = [
        r for r in results if r.get("_norm_symbols") and r["group_id"] not in ("QP-REF",)
    ]
    rows = []
    for i, a in enumerate(price_groups):
        for b in price_groups[i + 1 :]:
            common = sorted(set(a["_norm_symbols"]) & set(b["_norm_symbols"]))
            if common:
                rows.append(
                    {
                        "group_a": a["group_id"],
                        "group_b": b["group_id"],
                        "common_symbols": len(common),
                        "examples": common[:25],
                    }
                )
    return rows


# --------------------------------------------------------------------------------------
# Markdown rendering
# --------------------------------------------------------------------------------------
def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(x: Any) -> str:
        s = fmt_ts(x) if not isinstance(x, str) else x
        return s.replace("|", "\\|").replace("\n", " ")

    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def code_block(lines: list[str]) -> str:
    return "```\n" + "\n".join(lines) + "\n```"


def j(x: Any) -> str:
    return "`" + json.dumps(x, default=str, ensure_ascii=False) + "`"


def render_group(r: dict[str, Any]) -> str:
    L: list[str] = [f"## {r['group_id']} — {r['title']}", ""]
    L.append("### 1. Location & pattern")
    L.append(
        md_table(
            ["root", "pattern", "files", "total size", "extensions"],
            [
                [
                    f"`{r['root']}`",
                    ", ".join(f"`{p}`" for p in r["patterns"]),
                    str(r["file_count"]),
                    human_size(r["total_bytes"]),
                    j(r["extensions"]),
                ]
            ],
        )
    )
    if r.get("files_per_subfolder"):
        L.append("")
        L.append("Files per sub-folder: " + j(r["files_per_subfolder"]))
    L += ["", "### 2. Probable source", f"**{r['probable_source']}**", ""]
    L += [f"- {e}" for e in r["source_evidence"]]
    L += ["", "### 3–4. Symbols & asset class"]
    L.append(f"- Asset class guess: **{r['asset_class_guess']}**")
    if "symbol_count" in r:
        L.append(f"- {r['symbol_count']} symbols; first 30: {', '.join(r['symbols_first30'])}")
    if r["group_id"] == "QP-REF":
        L += ["", "### Tables"]
        L.append(
            md_table(
                ["file", "rows", "schema", "as_of values"],
                [
                    [t["file"], str(t["rows"]), j(t["schema"]), j(t["distinct_as_of"])]
                    for t in r.get("tables", [])
                ],
            )
        )
        rs = r.get("raw_samples", {})
        L += [
            "",
            f"Raw sample (`{rs.get('file')}`), head:",
            code_block(rs.get("head", [])),
            "tail:",
            code_block(rs.get("tail", [])),
        ]
        return "\n".join(L)
    for extra in r.get("_md_extra", []):
        L.append(extra)
    tfr = r.get("timeframe", {})
    L += [
        "",
        "### 5. Timeframe",
        f"- Dominant timeframe (median diff of consecutive timestamps, per file): **{tfr.get('dominant')}** in {tfr.get('files_median_eq_dominant')} of {r.get('deep_sample_files')} deep-sample files; "
        f"the other {tfr.get('files_median_other (sparse/illiquid: median gap > bar size)')} files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): {j(tfr.get('inferred_from_median_diff'))}",
        f"- Most frequent spacing per file (bar grid): {j(tfr.get('most_frequent_spacing_per_file'))} → mixed timeframes: {tfr.get('mixed')}; median share of diffs equal to the median: {tfr.get('median_share_of_diffs_eq_median')}",
    ]
    if r.get("stooq_PER_first_row_all_files"):
        L.append(
            f"- `<PER>` column value (first data row, all files; `null` = header-only file): {j(r['stooq_PER_first_row_all_files'])}"
        )
    if r.get("empty_files"):
        L.append(
            f"- **Empty files (no data rows):** {r['empty_files']} of {r['file_count']}; e.g. {', '.join(r['empty_file_examples'])}"
        )
    L += ["", "### 6. Date range"]
    dr = r.get("date_range_all_files", {})
    if dr:
        L.append(
            f"- Across all {r.get('light_pass_files')} files (light pass: head/tail lines or parquet min/max): first ts {j(dr['first_ts'])}; last ts {j(dr['last_ts'])}"
        )
    if r.get("futures_headers"):
        L.append("")
        L.append(
            md_table(
                [
                    "symbol",
                    "description",
                    "tag",
                    "exch",
                    "S.Start",
                    "S.End",
                    "$/pt",
                    "tick",
                    "first",
                    "last",
                    "size",
                ],
                [
                    [
                        h["symbol"],
                        h["description"],
                        h["contract_tag"],
                        h["Exchange"],
                        h["S.Start"],
                        h["S.End"],
                        h["$/Big Point"],
                        h["Tick Size"],
                        h["first"],
                        h["last"],
                        h["size"],
                    ]
                    for h in r["futures_headers"]
                ],
            )
        )
    elif r.get("per_symbol_range"):
        L.append("")
        L.append(
            md_table(
                ["symbol", "first", "last", "rows", "size"],
                [
                    [x["symbol"], x["first"], x["last"], str(x["rows"] or ""), x["size"]]
                    for x in r["per_symbol_range"]
                ],
            )
        )
    L += [
        "",
        "### 7. Schema",
        f"Representative file: `{r.get('representative_file')}`",
        "",
        j(r.get("schema")),
    ]
    cols = [c.lower().strip("<>") for c in (r.get("schema") or {})]
    has = {
        k: any(k in c for c in cols)
        for k in [
            "open",
            "high",
            "low",
            "close",
            "vol",
            "vwap",
            "trade",
            "bid",
            "ask",
            "spread",
            "openint",
        ]
    }
    L.append(f"\nColumn presence: {j(has)}")
    rs = r.get("raw_samples", {})
    L += ["", "### 8. Raw samples (verbatim)", f"File: `{rs.get('file')}`"]
    if rs.get("note"):
        L.append(f"_{rs['note']}_")
    L += [
        "",
        f"First {HEAD_ROWS} rows (with header lines):",
        code_block(rs.get("head", [])),
        f"Last {TAIL_ROWS} rows:",
        code_block(rs.get("tail", [])),
    ]
    L += ["", "### 9–12. Timestamp format, timezone, session, weekend, price type"]
    L += r.get("_md_ts", [])
    L += ["", "### 13–14. Adjustment / futures specifics"]
    L += r.get("_md_adj", [])
    q = r.get("quality", {})
    L += ["", "### 15. Quality quick-scan (deep sample)"]
    L.append(
        md_table(
            ["metric", "value"],
            [[k, j(v) if isinstance(v, dict) else str(v)] for k, v in q.items()],
        )
    )
    if r.get("deep_sampled"):
        L.append(
            f"\n_Per-file statistics computed on {r['deep_sample_files']} of {r['file_count']} files (task limit {MAX_DEEP_FILES}); "
            "`extrapolated_to_all_files` scales sample totals by file count and is an estimate._"
        )
    L.append(f"\nDeep-sample symbols: {', '.join(r.get('deep_sample_symbols', []))}")
    return "\n".join(L)


def most_common_merge(dicts: Iterable[dict[str, int]], n: int = 5) -> dict[str, int]:
    c: Counter[str] = Counter()
    for d in dicts:
        c.update(d)
    return dict(c.most_common(n))


def interpret(r: dict[str, Any], cross: dict[str, Any]) -> dict[str, Any]:
    """Derive the summary-level conclusions (timezone, bar label, price type, adjustment)
    from the measured evidence and attach markdown evidence bullets to the group."""
    gid = r["group_id"]
    sres = r.get("session_analysis", [])
    ts_md: list[str] = []
    adj_md: list[str] = []
    concl: dict[str, str] = {}
    fmt = {
        "qp_parquet": "parquet",
        "stooq": "txt (CSV)",
        "ms_csv": "csv",
        "ts_export": "txt (CSV + 7-line header)",
        "reference": "parquet + csv",
    }
    concl["format"] = fmt.get(r.get("_kind", ""), "?")
    concl["price_type"] = "trade (last-trade OHLC); no bid/ask/spread columns"

    splits = [s for s in cross["splits"] if s["group"] == gid]
    if splits:
        adj_md.append(
            "Split probes (previous close ÷ open on split date; ≈1 → split-adjusted, ≈factor → unadjusted):"
        )
        adj_md.append("")
        adj_md.append(
            md_table(
                ["ticker", "split", "factor", "prev close", "open", "ratio", "verdict"],
                [
                    [
                        s["ticker"],
                        f"{s['date']} (prev {s['prev_date']})",
                        str(s["factor"]),
                        str(s["prev_close"]),
                        str(s["open"]),
                        str(s["ratio_prev_close_to_open"]),
                        s["verdict"],
                    ]
                    for s in splits
                ],
            )
        )
        verdicts = {s["verdict"] for s in splits}
        split_v = (
            "split-adjusted"
            if verdicts == {"adjusted"}
            else ("unadjusted" if verdicts == {"unadjusted"} else "mixed/unclear")
        )
    else:
        split_v = "unknown (no split probe ticker/date in data)"
    pr = [p for p in cross["price_ratio_vs_ms"] if p["group"] == gid]
    if pr:
        adj_md.append("")
        adj_md.append(
            "Cross-source close ratio vs MS-US-1D (Alpaca SIP, adjustment=all), median per year. A ratio drifting away from 1 in older years indicates a different dividend-adjustment basis; flat ≈1 means same basis:"
        )
        adj_md.append("")
        adj_md.append(
            md_table(
                ["ticker", "common days", "close ratio by year", "volume ratio by year"],
                [
                    [
                        p["ticker"],
                        str(p["common_days"]),
                        j(p["median_close_ratio_by_year"]),
                        j(p["median_volume_ratio_by_year"]),
                    ]
                    for p in pr
                ],
            )
        )
        # split anomalies: whole years off by a large factor
        anomalies = sorted(
            {
                p["ticker"]
                for p in pr
                if any(v > 1.5 or v < 0.67 for v in p["median_close_ratio_by_year"].values())
            }
        )
        # dividend basis: dividend payers drift above 1 in older years when this source is not dividend-adjusted
        drift = []
        for p in pr:
            if p["ticker"] in ("KO", "XOM", "T", "JPM") and p["ticker"] not in anomalies:
                ys = sorted(p["median_close_ratio_by_year"])
                drift.append(
                    p["median_close_ratio_by_year"][ys[0]] - p["median_close_ratio_by_year"][ys[-1]]
                )
        if drift:
            div_adj = statistics.median(drift) < 0.01
            adj_md.append(
                f"\nDividend-payer drift (first-year minus last-year ratio, KO/XOM/T/JPM): {j([round(d, 4) for d in drift])} → "
                + (
                    "**same dividend basis as SIP adjustment=all (split + dividend adjusted)**."
                    if div_adj
                    else "**split-adjusted only, NOT dividend-adjusted** (older prices sit above the dividend-adjusted SIP series by the accumulated dividends)."
                )
            )
            split_v = (
                (
                    "split + dividend adjusted"
                    if div_adj
                    else "split-adjusted only (no dividend adj.)"
                )
                if split_v in ("split-adjusted", "mixed/unclear")
                else split_v
            )
        if anomalies:
            adj_md.append(
                f"\n**Anomaly:** {', '.join(anomalies)} — whole years differ from the SIP series by a split factor → split adjustment not applied consistently for these tickers."
            )
            split_v += f"; EXCEPTIONS: {', '.join(anomalies)} not adjusted for a split"
    concl["adjustment"] = split_v

    if gid in ("QP-US-EQ-1H", "QP-STOOQ-1H"):
        first = most_common_merge(s.get("ny_first_label_per_day", {}) for s in sres)
        last = most_common_merge(s.get("ny_last_label_per_day", {}) for s in sres)
        labels = most_common_merge((s.get("ny_label_counts", {}) for s in sres), 30)
        ts_md.append(
            f"- Bar labels converted to America/New_York — first label per day: {j(first)}; last label per day: {j(last)}"
        )
        ts_md.append(
            f"- All NY-local labels (count across sample): {j(dict(sorted(labels.items())))}"
        )
        ts_md.append(
            f"- Literal UTC probe: bars with UTC time in [08:00,13:30): {sum(s.get('bars_utc_0800_1330', 0) for s in sres)}; bars ≥ 20:00 UTC: {sum(s.get('bars_utc_ge_2000', 0) for s in sres)}"
            " (note: 13:00–13:30 UTC is inside RTH-hour-aligned bars in summer, so the NY-local probe below is the meaningful one)"
        )
        ts_md.append(
            f"- NY-local probe: bars labelled before 09:00 ET: {sum(s.get('bars_ny_before_0900', 0) for s in sres)}; labelled ≥ 16:00 ET: {sum(s.get('bars_ny_at_or_after_1600', 0) for s in sres)}; ≥ 17:00 ET: {sum(s.get('bars_ny_at_or_after_1700', 0) for s in sres)}"
        )
        ts_md.append(
            f"- UTC first label per day, NY summer (EDT): {j(most_common_merge(s.get('utc_first_label_summer', {}) for s in sres))}; NY winter (EST): {j(most_common_merge(s.get('utc_first_label_winter', {}) for s in sres))} → a 1-hour shift in UTC between seasons means timestamps track the US exchange clock correctly after conversion."
        )
        ts_md.append(
            f"- Bars per NY day: {j(most_common_merge({str(k): v for k, v in s.get('bars_per_day', {}).items()} for s in sres))}"
        )
        ts_md.append(
            f"- Half-days in sample: {j([s.get('half_days') for s in sres if s.get('half_days')][:3])}"
        )
        ts_md.append(
            f"- Bars on NYSE full holidays: {sum(len(s.get('bars_on_holidays', [])) for s in sres)} (files with any: {sum(1 for s in sres if s.get('bars_on_holidays'))})"
        )
        if gid == "QP-US-EQ-1H":
            ts_md.insert(
                0, "- Stored as `datetime[μs, UTC]` (tz-aware) → timezone explicit: **UTC**."
            )
            vt = sum(s.get("volume_total", 0.0) for s in sres)
            ve = sum(s.get("volume_ext_labels", 0.0) for s in sres)
            main = {k: v for k, v in labels.items() if v > 0.5 * max(labels.values())}
            concl["timezone"] = "UTC (tz-aware)"
            concl["bar_label"] = "bar-start (hour-aligned)"
            ts_md.append(
                f"- Interpretation: the regular labels are {min(main)}–{max(main)} ET (7 per day, no 09:30 label) → **bar-start of hour-aligned bars** "
                f"(a bar-end convention would need a 16:00 label every day). Sparse extra labels {j({k: v for k, v in labels.items() if k not in main})} are **extended-hours bars** "
                f"(08:00 = 08:00–09:00 pre-market, 16:00 = 16:00–17:00 after-hours) carrying {100 * ve / vt:.2f}% of volume → the data is **not RTH-filtered**; "
                "the 09:00 bar therefore most likely also contains 09:00–09:30 pre-market prints."
            )
        else:
            nf = most_common_merge(s.get("raw_first_label_normal", {}) for s in sres)
            mf = most_common_merge(s.get("raw_first_label_us_eu_dst_mismatch", {}) for s in sres)
            nl = most_common_merge(s.get("raw_last_label_normal", {}) for s in sres)
            ml = most_common_merge(s.get("raw_last_label_us_eu_dst_mismatch", {}) for s in sres)
            raw = most_common_merge((s.get("raw_label_counts", {}) for s in sres), 30)
            ts_md.insert(
                0, "- `<DATE>` = `YYYYMMDD` int, `<TIME>` = `HHMMSS` int, **naive** (no offset)."
            )
            ts_md.insert(1, f"- Raw wall-clock labels (as stored): {j(dict(sorted(raw.items())))}")
            ts_md.insert(
                2,
                f"- DST test — raw first/last label per day on normal days: {j(nf)} / {j(nl)}; on days when US DST and EU DST disagree (2nd Sun Mar→last Sun Mar, last Sun Oct→1st Sun Nov): {j(mf)} / {j(ml)} "
                f"(days: normal {sum(s.get('days_normal', 0) for s in sres)}, mismatch {sum(s.get('days_us_eu_dst_mismatch', 0) for s in sres)}). "
                "A one-hour shift in the mismatch window means the clock is **European local time (CET/CEST)**, not US time and not UTC.",
            )
            ts_md.insert(
                3,
                f"- Local times that do not exist in Europe/Warsaw (spring-forward): {sum(s.get('nonexistent_local_times', 0) for s in sres)}",
            )
            concl["timezone"] = "naive Europe/Warsaw (CET/CEST) wall clock"
            has_1600 = "16:00" in labels
            concl["bar_label"] = "bar-end" if has_1600 else "bar-start"
            ts_md.append(
                f"- Interpretation: after Warsaw→UTC→NY conversion, labels run {min(labels)}–{max(labels)} ET; label 16:00 ET present and 09:30 absent → labels are **bar-end** (first bar 09:30–10:00 labelled 10:00, last bar 15:00–16:00 labelled 16:00)."
                if has_1600
                else f"- Interpretation: labels run {min(labels)}–{max(labels)} ET."
            )
            ts_md.append(
                "- Half-day caveat: on NYSE half-days (close 13:00 ET) the sample shows 5 bars with the last label 14:00 ET (20:00 CET), and in the raw files that last bar carries the day's largest volume (closing auction). "
                "A strict bar-end reading would give 4 bars ending 13:00, so how Stooq bins the closing print is not fully determined."
            )
            per = r.get("stooq_PER_first_row_all_files", {})
            ts_md.append(
                f"- `<PER>` = {j(per)} (60 = hourly in Stooq); `<OPENINT>` present but always 0 for stocks (see samples)."
            )
    elif gid in ("QP-US-EQ-1D", "MS-US-1D"):
        wd = most_common_merge((s.get("weekday_counts", {}) for s in sres), 7)
        ts_md.append(f"- Weekday distribution (sample): {j(wd)}")
        hol = sum(len(s.get("rows_on_nyse_holidays", [])) for s in sres)
        ts_md.append(
            f"- Rows on NYSE full-holiday dates {j([str(h) for h in US_HOLIDAYS])}: {hol} (files with any: {sum(1 for s in sres if s.get('rows_on_nyse_holidays'))})"
        )
        if gid == "QP-US-EQ-1D":
            conv = r.get("daily_ts_time_of_day_conventions_all_files", {})
            z = r.get("files_with_0000_utc_convention", [])
            ts_md.insert(
                0,
                f"- Stored as `datetime[μs, UTC]`. Distinct time-of-day sets per file (all {r['file_count']} files): {j(conv)}. "
                "`04:00,05:00` = Alpaca's native daily stamp (midnight America/New_York → 04:00 UTC in EDT, 05:00 UTC in EST); "
                f"`00:00` = session date re-stamped at 00:00 UTC. **Two conventions coexist** — {len(z)} files use 00:00 UTC, e.g. {', '.join(z[:20])}.",
            )
            concl["timezone"] = (
                "UTC; MIXED: midnight-NY (04/05 UTC) in most files, 00:00 UTC in some"
            )
        else:
            ts_md.insert(
                0, "- `date` column is `YYYY-MM-DD` text, no time, no zone (session date)."
            )
            concl["timezone"] = "date only (session date)"
        concl["bar_label"] = "session date"
    elif gid == "QP-CRYPTO-1H":
        wd = most_common_merge((s.get("weekday_counts", {}) for s in sres), 7)
        ts_md.append("- Stored as `datetime[μs, UTC]` (tz-aware).")
        ts_md.append(
            f"- Weekday distribution: {j(wd)} → 24/7 incl. weekends; distinct hours per file (min): {min((s.get('distinct_hours', 0) for s in sres), default=0)}; minute labels: {j(most_common_merge(s.get('minute_labels', {}) for s in sres))}"
        )
        ts_md.append(
            "- Bar label: ccxt `fetch_ohlcv` timestamps are bar-open times (exchange convention) → **bar-start** (not verifiable from data alone)."
        )
        ts_md.append(
            f"- Largest gap in any sampled file: {max((s.get('largest_gap_hours', 0) for s in sres), default=0):.0f} h"
        )
        concl["timezone"] = "UTC (tz-aware)"
        concl["bar_label"] = "bar-start (ccxt convention)"
        concl["adjustment"] = "n/a (crypto)"
        for c in cross["crypto"]:
            adj_md.append(
                f"- Cross-source {c['pair']}: QP (hourly→UTC day) vs MS-CRYPTO-1D (Binance daily): {c['common_days']} common days, median close ratio {c['median_close_ratio_QP_over_MS']}, p99 |dev| {c['p99_abs_close_ratio_dev']}, median volume ratio {c['median_volume_ratio_QP_over_MS']} (volume ratio ≪1 → different, thinner venue)."
            )
    elif gid in ("MS-CRYPTO-1D", "MS-PIT-CRYPTO-1D"):
        wd = most_common_merge((s.get("weekday_counts", {}) for s in sres), 7)
        ts_md.append(
            "- `date` text `YYYY-MM-DD`, no time/zone. Binance daily candles open 00:00 UTC → date = UTC day (convention, not verifiable from file)."
        )
        ts_md.append(f"- Weekday distribution: {j(wd)} → 7-day week.")
        concl["timezone"] = "date only (UTC day, exchange convention)"
        concl["bar_label"] = "session date"
        concl["adjustment"] = "n/a (crypto)"
    elif gid == "MS-IRAN-1D":
        wd = most_common_merge((s.get("weekday_counts", {}) for s in sres), 7)
        ts_md.append("- `date` text `YYYY-MM-DD` (Gregorian), no time/zone.")
        ts_md.append(
            f"- Weekday distribution: {j(wd)} → Tehran trading week (Sat–Wed); Thu/Fri rows indicate calendar changes or data artefacts."
        )
        concl["timezone"] = "date only (Asia/Tehran session date)"
        concl["bar_label"] = "session date"
        bm = r.get("quality", {}).get("files_with_big_moves", 0)
        adj_md.append(
            f"- No well-known split probes exist for TSE. Proxy: {bm} of {r.get('deep_sample_files')} sampled files have ≥1 day-to-day close move > {int(BIG_MOVE * 100)}%, although TSE daily price limits are a few percent → capital increases/dividends appear as raw jumps → **likely unadjusted** (to confirm)."
        )
        concl["adjustment"] = "likely unadjusted (jumps beyond daily limits)"
    elif gid == "ME-FUT-15M":
        ts_md.append("- `Date` = `MM/DD/YYYY`, `Time` = `HH:MM`, **naive**, separate columns.")
        ss = sum(s.get("label_eq_session_start", 0) for s in sres)
        se = sum(s.get("label_eq_session_end", 0) for s in sres)
        sp = sum(s.get("label_eq_session_start_plus_tf", 0) for s in sres)
        ts_md.append(
            f"- Across the sample, bars labelled exactly at header `S.Start`: {ss}; at `S.Start`+15 min: {sp}; at `S.End`: {se}. S.End present and S.Start (almost) absent → labels are **bar-end** (TradeStation convention)."
        )
        es = next((s for s in sres if s.get("symbol") == "@ES"), None)
        if es:
            ts_md.append(
                f"- @ES first bar of each session, winter (Dec–Feb): {j(es.get('session_first_label_winter'))}; summer (Jun–Aug): {j(es.get('session_first_label_summer'))} → identical wall-clock across DST ⇒ timestamps are **exchange-local time (US/Central for CME, with DST)**, not UTC."
            )
            ts_md.append(
                f"- @ES weekday counts: {j(es.get('weekday_counts'))} → Sunday bars are the Globex evening open (17:00 CT Sunday)."
            )
        ex = Counter(h.get("Exchange") for h in r.get("futures_headers", []))
        ts_md.append(
            f"- Exchanges in headers: {j(dict(ex))} — ICE/NYBOT softs would be exported in their own local (US/Eastern) time if TradeStation's default 'exchange time' setting was used (to confirm)."
        )
        concl["timezone"] = "naive exchange-local (US/Central for CME/CBOT/NYMEX)"
        concl["bar_label"] = "bar-end"
        neg = sum(s.get("negative_or_zero_prices", 0) for s in sres)
        adj_md.append(
            f"- Series type: every header says `Continuous Contract [Dec23]` → **continuous series** (one file per root), ending with the Dec-2023 contract; all files end on {r['date_range_all_files'].get('last_ts', {}).get('max')}."
        )
        adj_md.append(
            f"- Bars with low ≤ 0 across sample: {neg} (back-adjusted series can go negative)."
        )
        neg_syms = [
            f"{s['symbol']} ({s['negative_or_zero_prices']})"
            for s in sres
            if s.get("negative_or_zero_prices", 0) > 0
        ]
        adj_md.append(
            f"- Contracts with bars at price ≤ 0: {', '.join(neg_syms) or 'none'}. Real prices of these contracts never went ≤ 0 (except WTI crude in April 2020), so this is the signature of **additive back-adjustment**."
        )
        qshare = [s.get("top20_jumps_in_quarterly_roll_window_share", float("nan")) for s in sres]
        qshare = [q for q in qshare if not math.isnan(q)]
        adj_md.append(
            f"- Roll gaps: median share of each contract's 20 largest open-vs-previous-close jumps that fall in a quarterly roll window (5th–16th of Mar/Jun/Sep/Dec ≈ 13% of days): {statistics.median(qshare) if qshare else float('nan'):.2f} → "
            "no clustering at roll dates; the largest jumps are weekend/news gaps → roll gaps have been removed (consistent with back-adjusted continuous series)."
        )
        rows = []
        for s in sres:
            rows.append(
                [
                    s["symbol"],
                    str(s.get("negative_or_zero_prices", 0)),
                    str(round(s.get("tick_grid_share_first20k_close", float("nan")), 3)),
                    str(round(s.get("tick_grid_share_last20k_close", float("nan")), 3)),
                    str(
                        round(s.get("top20_jumps_in_quarterly_roll_window_share", float("nan")), 2)
                    ),
                    j(s.get("top_jumps", [])[:2]),
                ]
            )
        adj_md.append("")
        adj_md.append(
            "Tick-grid test (share of closes that are exact multiples of the header tick size; additive back-adjustment keeps prices on the grid, ratio adjustment breaks it) and largest open-vs-previous-close jumps (in multiples of the rolling median bar range; roll gaps would cluster in roll windows):"
        )
        adj_md.append("")
        adj_md.append(
            md_table(
                [
                    "symbol",
                    "bars ≤ 0",
                    "on-grid first 20k",
                    "on-grid last 20k",
                    "top-20 jumps in Mar/Jun/Sep/Dec 5–16",
                    "top 2 jumps",
                ],
                rows,
            )
        )
        concl["adjustment"] = (
            "continuous, additive back-adjusted (negative prices, no roll gaps); roll rule unknown"
        )
    if gid == "MS-US-1D" and "split" in concl.get("adjustment", ""):
        concl["adjustment"] = (
            "split + dividend adjusted (splits: probes; dividends: adjustment=all in downloader code)"
        )
    r["_md_ts"] = ts_md
    r["_md_adj"] = adj_md
    r["conclusions"] = concl
    return concl


def render_markdown(
    results: list[dict[str, Any]],
    cross: dict[str, Any],
    ovl: list[dict[str, Any]],
    meta: dict[str, Any],
    questions: list[str],
    extra_sections: list[str],
) -> str:
    L = [
        "# Data inventory (T00 · F-0.1.12)",
        "",
        f"Generated {meta['generated_utc']} by `scripts/data_inventory.py` in {meta['elapsed_s']} s. Read-only scan.",
        "",
        f"**Source integrity check:** {meta['integrity']['files_checked']} source files stat-ed before and after the run (+ {meta['integrity']['evidence_files_checked']} evidence files outside the roots: logs, manifests, downloader code); changed: {meta['integrity']['changed']}, added: {meta['integrity']['added']}, removed: {meta['integrity']['removed']} → **{'no source file was modified' if meta['integrity']['ok'] else 'CHANGES DETECTED'}**.",
        "",
        "Source roots:",
        *[f"- `{k}`: `{v}`" for k, v in meta["roots"].items()],
        "",
        "Method: every file gets a *light pass* (size, symbol, first/last timestamp from the head/tail lines or parquet min/max); "
        f"at most {MAX_DEEP_FILES} files per group get a *deep pass* (full read: timeframe, sessions, timezone tests, quality). "
        "Deep-sample files = priority tickers (split probes / cross-source tickers) + evenly spaced files from the sorted list.",
        "",
        "## Summary",
        "",
    ]
    rows = []
    for r in results:
        c = r.get("conclusions", {})
        dr = r.get("date_range_all_files", {})
        rng = f"{dr['first_ts']['min'][:10]} → {dr['last_ts']['max'][:10]}" if dr else "—"
        tf = (r.get("timeframe") or {}).get("dominant") or "—"
        rows.append(
            [
                r["group_id"],
                r["probable_source"],
                r["asset_class_guess"],
                str(r.get("symbol_count", "—")),
                tf,
                rng,
                c.get("format", "—"),
                f"{c.get('timezone', '—')}; {c.get('bar_label', '')}",
                c.get("price_type", "—") if r["group_id"] != "QP-REF" else "—",
                c.get("adjustment", "—"),
                "; ".join(r.get("summary_notes", [])),
            ]
        )
    L.append(
        md_table(
            [
                "group",
                "source",
                "asset class",
                "#symbols",
                "timeframe",
                "date range",
                "format",
                "timezone; bar label",
                "price type",
                "adjustment",
                "notes",
            ],
            rows,
        )
    )
    L += ["", "## Overlaps (same normalised symbol in more than one group)", ""]
    L.append(
        "Normalisation: upper-case, separators `. - / _` removed (e.g. `BRK.B`=`BRK-B`=`BRKB`, `BTC_USDT`=`BTCUSDT`)."
    )
    L.append("")
    L.append(
        md_table(
            ["group A", "group B", "# common", "examples (first 25)"],
            [
                [o["group_a"], o["group_b"], str(o["common_symbols"]), ", ".join(o["examples"])]
                for o in ovl
            ],
        )
    )
    L += extra_sections
    L += ["", "## Questions for the user", ""]
    L += [f"{i}. {q}" for i, q in enumerate(questions, 1)]
    L += ["", "## Files that could not be read", ""]
    if meta["errors"]:
        L.append(
            md_table(
                ["group", "file", "stage", "error"],
                [
                    [e["group"], e["file"], e.get("stage", ""), e["error"][:200]]
                    for e in meta["errors"][:100]
                ],
            )
        )
        if len(meta["errors"]) > 100:
            L.append(f"\n… {len(meta['errors']) - 100} more in the JSON.")
    else:
        L.append("None.")
    L += ["", "---", ""]
    for r in results:
        L += [render_group(r), "", "---", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items() if not str(k).startswith("_")}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (dt.datetime, dt.date)):
        return x.isoformat()
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    return x


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--quantplatform", type=Path, default=DEFAULT_SRC / "QuantPlatform" / "data")
    ap.add_argument(
        "--marketscanner", type=Path, default=DEFAULT_SRC / "MarketScanner" / "data" / "candles"
    )
    ap.add_argument(
        "--marketedge", type=Path, default=DEFAULT_SRC / "MarketEdge" / "Data" / "Futures"
    )
    ap.add_argument("--dukascopy", type=Path, default=None, help="Dukascopy data folder (none yet)")
    ap.add_argument("--out-md", type=Path, default=REPO / "docs" / "data_inventory.md")
    ap.add_argument("--out-json", type=Path, default=REPO / "docs" / "data_inventory.json")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    roots = {
        "QuantPlatform": args.quantplatform,
        "MarketScanner candles": args.marketscanner,
        "MarketEdge futures": args.marketedge,
    }
    if args.dukascopy:
        roots["Dukascopy"] = args.dukascopy
    for k, v in roots.items():
        if not v.exists():
            print(f"[warn] root missing: {k} -> {v}")
    t0 = time.time()
    print("[snapshot] stat-ing source trees (before)...")
    before = snapshot_tree(v for v in roots.values() if v.exists())

    groups = build_groups(args.quantplatform, args.marketscanner, args.marketedge)
    kinds = {g.gid: g.kind for g in groups}
    errors: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    for g in groups:
        print(f"[group] {g.gid} ...", flush=True)
        r = process_group(g, errors)
        r["_kind"] = kinds[g.gid]
        results.append(r)
        print(f"        {r['file_count']} files, {r.get('elapsed_s')} s", flush=True)

    # files under the roots not covered by any group
    covered = {i["path"] for r in results for i in r.get("_light", [])}
    covered |= {str(Path(r["root"]) / t["file"]) for r in results for t in r.get("tables", [])}
    uncovered = sorted(p for p in before if p not in covered)

    cross = cross_checks(results)
    ovl = overlaps(results)
    for r in results:
        if r["group_id"] != "QP-REF":
            interpret(r, cross)
        else:
            r["conclusions"] = {
                "format": "parquet + csv",
                "timezone": "as_of date",
                "bar_label": "",
                "adjustment": "n/a",
            }

    # --- group-specific notes and extra sections
    by = {r["group_id"]: r for r in results}
    extra: list[str] = []
    ms_manifest = args.marketscanner.parent / "symbols.csv"
    if ms_manifest.is_file():
        man = pl.read_csv(track(ms_manifest), infer_schema_length=0)
        vc = (
            man.group_by(["market_slug", "source_key"], maintain_order=True)
            .len()
            .sort(["len", "market_slug", "source_key"], descending=[True, False, False])
        )
        by["MS-US-1D"]["manifest_source_keys"] = [
            dict(zip(vc.columns, row, strict=False)) for row in vc.iter_rows()
        ]
        extra += ["", "## MarketScanner manifest (`data/symbols.csv`, read-only corroboration)", ""]
        extra.append(
            f"{man.height} rows (the candles folder holds {sum(by[g]['file_count'] for g in ['MS-US-1D', 'MS-CRYPTO-1D', 'MS-PIT-CRYPTO-1D', 'MS-IRAN-1D'])} files → the manifest covers only part of them)."
        )
        extra.append("")
        extra.append(
            md_table(
                ["market_slug", "source_key", "rows"],
                [[str(a), str(b), str(c)] for a, b, c in vc.iter_rows()],
            )
        )
    iran_meta = args.marketscanner.parent / "iran_meta.csv"
    if iran_meta.is_file():
        im = pl.read_csv(track(iran_meta), infer_schema_length=0)
        names = im["name"].fill_null("")
        kinds_fa = {
            "صندوق (fund/ETF)": names.str.contains("صندوق", literal=True).sum(),
            "مرابحه (murabaha sukuk)": names.str.contains("مرابحه", literal=True).sum(),
            "اجاره (ijara sukuk)": names.str.contains("اجاره", literal=True).sum(),
            "مشارکت (participation bond)": names.str.contains("مشارکت", literal=True).sum(),
            "اسناد خزانه (treasury bill)": names.str.contains("اسناد خزانه", literal=True).sum(),
            "حق تقدم (rights)": names.str.contains("حق تقدم", literal=True).sum(),
        }
        ins_in_files = set(by["MS-IRAN-1D"].get("_symbols_all", []))
        matched = im.filter(pl.col("ins").is_in(list(ins_in_files))).height
        extra += [
            "",
            "## Iran instrument types (`data/iran_meta.csv`, read-only corroboration)",
            "",
        ]
        extra.append(
            f"{im.height} rows; {matched} of {len(ins_in_files)} candle files have a matching `ins` code. Name-keyword counts (whole meta file):"
        )
        extra.append("")
        extra.append(md_table(["keyword", "rows"], [[k, str(int(v))] for k, v in kinds_fa.items()]))
    if uncovered:
        extra += ["", "## Files under the source roots not assigned to any group", ""]
        extra.append(
            code_block(
                uncovered[:50]
                + ([f"... {len(uncovered) - 50} more"] if len(uncovered) > 50 else [])
            )
        )

    # summary notes
    def add_note(gid: str, s: str) -> None:
        by[gid].setdefault("summary_notes", []).append(s)

    for r in results:
        if r.get("deep_sampled"):
            add_note(
                r["group_id"], f"deep stats on {r['deep_sample_files']}/{r['file_count']} files"
            )
    for gid in ("QP-US-EQ-1D", "QP-US-EQ-1H", "QP-STOOQ-1H", "MS-US-1D", "MS-IRAN-1D"):
        if by[gid].get("empty_files"):
            add_note(gid, f"{by[gid]['empty_files']} empty files")
    add_note("QP-US-EQ-1D", "IEX-only volume (≈1–4% of SIP)")
    add_note("QP-US-EQ-1D", "two timestamp conventions")
    add_note(
        "QP-US-EQ-1H",
        "IEX-only volume; sparse 08:00/16:00 ET extended-hours bars (not RTH-filtered)",
    )
    add_note("QP-STOOQ-1H", "only ≈2 years of history; volume ≈55–85% of SIP daily")
    add_note("MS-CRYPTO-1D", "PAXG_USDT appears twice (crypto_ and gold_ prefix)")
    add_note("MS-IRAN-1D", "includes funds, sukuk, rights")
    add_note("MS-PIT-CRYPTO-1D", "includes delisted pairs (survivorship-free)")
    if "2023-11-01" in json.dumps(by["ME-FUT-15M"].get("date_range_all_files", {}), default=str):
        add_note("ME-FUT-15M", "all series end 2023-11-01 (stale)")
    add_note("QP-REF", "not price data")

    # --- questions
    questions = [
        "Dukascopy: no Dukascopy data exists yet (confirmed by you). Where will the minute bid/ask data be downloaded to, and which symbols (FX majors, XAUUSD, index CFDs such as USA500IDXUSD / USA30IDXUSD)? The spec relies on it for spread profiles and FX/metal/CFD research.",
        "US equities — reference source: QP-US-EQ-1D/1H are Alpaca **IEX** (volume is a small fraction of the consolidated tape), MS-US-1D is Alpaca **SIP** daily, QP-STOOQ-1H is Stooq hourly. Which is the reference source for US equities per timeframe? (Suggestion to decide: SIP for daily; for hourly only IEX or Stooq exist today.)",
        "Is there an Alpaca SIP **hourly** download anywhere (the spec prefers SIP + RTH filter)? If not, should T04 include a downloader or should we use IEX/Stooq hourly for now?",
        "QP-US-EQ-1H is hour-aligned bar-start (09:00–15:00 ET) and NOT RTH-filtered (sparse 08:00 and 16:00 ET extended-hours bars exist). The 09:00 bar therefore probably mixes 09:00–09:30 pre-market with the first 30 RTH minutes. Is this data acceptable for 1h research, or should hourly bars be rebuilt from minute data with an RTH filter (09:30-anchored bars)?",
        "QuantPlatform AVGO: the QP series is not adjusted for the 2024-07-15 10:1 split (prices ×10 before the split vs. SIP), while other split tickers are adjusted. Probably the file was downloaded before the split and later extended incrementally. Should QP data be re-downloaded, or do we treat MS-US-1D (SIP) as the reference and QP only as a fallback?",
        "Stooq hourly is split-adjusted but NOT dividend-adjusted (older prices of dividend payers sit 1–8% above the SIP adjustment=all series). Which price basis should the canonical store use: raw/split-only (TradingView-like, needed for parity) or total-return adjusted? Also, Stooq intraday history covers only ≈2 years (2024-06 →). Is that enough for the 1h research track?",
        "Stooq half-days show a 5th bar labelled 14:00 ET that holds the closing auction. How should Stooq bars be binned on half-days (drop, merge into the last RTH bar, keep)?",
        "Futures (MarketEdge): exported from TradeStation or MultiCharts? Which back-adjustment setting was used (TradeStation default for `@` symbols is *not* back-adjusted unless enabled; the data suggests back-adjusted — please confirm), and which roll rule (volume-based / N days before expiry)?",
        "Futures timestamps: confirm the export used **exchange time** (US/Central for CME/CBOT/NYMEX/COMEX; US/Eastern for ICE softs) rather than the PC local time.",
        "Futures data ends 2023-11-01 for every file. Is a refreshed export planned? Are the ICE softs, VIX futures and the `.D` (day-session) variants in scope?",
        "Crypto: two sources disagree on venue — QP-CRYPTO-1H (binanceus hourly, thin volume) vs MS crypto daily (Binance global). Is crypto in scope for Strategy Factory at all? If yes, which venue is the reference?",
        "Iran (TSE/Farabourse, 2365 instruments incl. funds and sukuk): in scope for Strategy Factory? If yes we need an adjustment policy (capital increases/dividends appear unadjusted) and a session/calendar definition (Sat–Wed, Asia/Tehran).",
        "QuantPlatform `us_equity` holds 6362 daily and 5887 hourly files: were delisted tickers included (survivorship) or only currently active symbols? `reference/assets` lists status active/inactive — should it drive the universe?",
        "Auxiliary series (VIX index, SPX index, rates) from Yahoo: none found in these folders. Where should they come from?",
        "Execution broker(s) for cost profiles are still open (HANDOFF §7.3) — no broker/MT5 exports were found in the scanned folders.",
    ]
    security = code_evidence(
        DEFAULT_SRC / "MarketScanner" / "scripts" / "host_download.py",
        r"ALPACA_KEY = os\.environ\.get",
        1,
    )
    if security:
        questions.append(
            "Security (outside scope, noticed while collecting source evidence): `MarketScanner/scripts/host_download.py` and `host_download_us_pit.py` contain a hard-coded fallback Alpaca API key in `os.environ.get(...)`. Consider rotating that key and removing the default. (Value not reproduced here.)"
        )

    after = snapshot_tree(v for v in roots.values() if v.exists())
    changed = [k for k in before if k in after and before[k] != after[k]]
    added = [k for k in after if k not in before]
    removed = [k for k in before if k not in after]
    for k, v in EVIDENCE_STAT.items():
        st = Path(k).stat()
        if (st.st_size, st.st_mtime_ns) != v:
            changed.append(k)
    meta = {
        "generated_utc": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "elapsed_s": round(time.time() - t0, 1),
        "roots": {k: str(v) for k, v in roots.items()},
        "dukascopy": str(args.dukascopy)
        if args.dukascopy
        else "not provided — user confirmed no Dukascopy data yet",
        "integrity": {
            "files_checked": len(before),
            "evidence_files_checked": len(EVIDENCE_STAT),
            "changed": len(changed),
            "added": len(added),
            "removed": len(removed),
            "ok": not (changed or added or removed),
            "changed_files": changed[:50],
        },
        "errors": errors,
        "uncovered_files": uncovered,
        "python": sys.version.split()[0],
        "polars": pl.__version__,
    }
    md = render_markdown(results, cross, ovl, meta, questions, extra)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(md, encoding="utf-8")
    payload = {
        "meta": meta,
        "groups": jsonable(results),
        "overlaps": ovl,
        "cross_source_checks": jsonable(cross),
        "questions_for_user": questions,
    }
    args.out_json.write_text(
        json.dumps(jsonable(payload), indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(
        f"[done] {args.out_md} and {args.out_json} written in {meta['elapsed_s']} s; integrity ok={meta['integrity']['ok']}; errors={len(errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
