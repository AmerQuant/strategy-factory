"""TradingView parity references (T11 §1, D-348): read-only, verified, used **as exported**.

Two kinds of file live in ``SFAC_RAW_ROOT/reference/tradingview/parity/``:

* **chart data** -- a TradingView "Export chart data" CSV, ``time,open,high,low,close`` with
  ``time`` in UNIX seconds. The stamp is the **bar open in UTC**; a SPY daily bar is stamped
  14:30 UTC (09:30 New York), not 00:00 UTC.
* **trade list** -- a Strategy Tester "List of trades" export, two rows per trade (entry and
  exit) or one row per trade depending on the export; both shapes are read.

**The bars are used exactly as exported** (D-348): no D-010 Sunday merge, no resampling, no
re-bucketing to 00:00 UTC, no Alpaca or Dukascopy bars. A parity run is a comparison against
TradingView, so anything we "fix" first would be the thing we are trying to measure.

**Provenance (as in D-340).** ``manifest.json`` next to the files lists every file with its
SHA-256 and row count; :func:`load_chart_data` and :func:`load_trade_list` **verify the hash on
every load** and raise when it differs or the manifest is missing. The folder is never written
to (CLAUDE.md rule 11): ``scripts/write_parity_manifest.ps1`` is run by the user (D-031).

The references are **not snapshots**: they never enter the catalog, the snapshot store or
``SFAC_DATA_ROOT``.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from strategy_factory.core.errors import ConfigError, DataError

PARITY_DIR = Path("reference") / "tradingview" / "parity"
MANIFEST = "manifest.json"
CHART_COLUMNS = ("time", "open", "high", "low", "close")
F64 = npt.NDArray[np.float64]
I64 = npt.NDArray[np.int64]
#: Trade-list column names TradingView has used, lower-cased and stripped.
_TRADE_ALIASES: dict[str, tuple[str, ...]] = {
    "trade": ("trade #", "trade"),
    "type": ("type",),
    "signal": ("signal", "signal name"),
    "datetime": ("date/time", "date time", "datetime"),
    "price": ("price usd", "price", "price (usd)"),
    "quantity": ("contracts", "quantity", "position size"),
    "pnl": ("profit usd", "profit (usd)", "p&l usd", "net profit usd"),
    "cumulative": ("cumulative profit usd", "cum. profit usd", "cumulative p&l usd"),
}


# --------------------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------------------
def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(folder: Path) -> dict[str, dict[str, Any]]:
    """``{file name: {sha256, rows, ...}}`` from ``manifest.json``; a missing one is an error."""
    path = folder / MANIFEST
    if not path.is_file():
        raise ConfigError(
            "parity manifest not found; run scripts/write_parity_manifest.ps1 (D-031, D-348)",
            config_path=path,
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read the parity manifest: {exc}", config_path=path) from exc
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict) or not files:
        raise ConfigError("parity manifest has no 'files' mapping", config_path=path)
    return {str(name): dict(entry) for name, entry in files.items()}


def verify(path: Path, manifest: dict[str, dict[str, Any]] | None = None) -> str:
    """Check ``path`` against the manifest and return its SHA-256 (D-340)."""
    entries = manifest if manifest is not None else load_manifest(path.parent)
    entry = entries.get(path.name)
    if entry is None:
        raise ConfigError(
            f"{path.name} is not listed in {MANIFEST}; every parity reference must be",
            config_path=path.parent / MANIFEST,
        )
    recorded = str(entry.get("sha256", ""))
    actual = sha256_of(path)
    if recorded != actual:
        raise DataError(
            f"{path.name}: sha256 {actual[:12]}… does not match the manifest's "
            f"{recorded[:12] or '(none)'}… -- the parity references are immutable (D-348)",
            stage="parity",
        )
    return actual


# --------------------------------------------------------------------------------------
# Chart data (OHLC)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ChartData:
    """A TradingView chart export, exactly as exported (D-348)."""

    name: str
    sha256: str
    ts: I64  # UNIX seconds, bar open, UTC
    open: F64
    high: F64
    low: F64
    close: F64

    def __len__(self) -> int:
        return int(self.ts.shape[0])

    @property
    def ts_us(self) -> I64:
        """Bar starts in microseconds UTC -- the engine's timestamp unit."""
        return self.ts.astype(np.int64) * 1_000_000

    def range(self) -> tuple[dt.datetime, dt.datetime]:
        first, last = int(self.ts[0]), int(self.ts[-1])
        return (
            dt.datetime.fromtimestamp(first, dt.UTC),
            dt.datetime.fromtimestamp(last, dt.UTC),
        )

    def bars(self) -> dict[str, Any]:
        """The mapping ``run_backtest`` takes (``ts`` in microseconds UTC, OHLC)."""
        return {
            "ts": self.ts_us,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
        }

    def index_of(self, when: dt.datetime) -> int:
        """Index of the bar whose stamp is ``when``; a stamp that is not a bar start raises."""
        target = int(when.astimezone(dt.UTC).timestamp())
        idx = int(np.searchsorted(self.ts, target))
        if idx >= len(self) or int(self.ts[idx]) != target:
            raise DataError(
                f"{self.name}: {when.isoformat()} is not a bar start in the export",
                stage="parity",
            )
        return idx


def load_chart_data(path: Path, manifest: dict[str, dict[str, Any]] | None = None) -> ChartData:
    """Read a TradingView chart export; the bars are **not** touched (D-348)."""
    sha = verify(path, manifest)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise DataError(f"{path.name}: no rows", stage="parity")
    missing = [c for c in CHART_COLUMNS if c not in rows[0]]
    if missing:
        raise DataError(f"{path.name}: missing column(s) {missing}", stage="parity")
    ts = np.array([int(r["time"]) for r in rows], dtype=np.int64)
    if np.any(np.diff(ts) <= 0):
        raise DataError(f"{path.name}: timestamps are not strictly increasing", stage="parity")
    cols = {c: np.array([float(r[c]) for r in rows], dtype=np.float64) for c in CHART_COLUMNS[1:]}
    if np.any(cols["high"] < cols["low"]):
        raise DataError(f"{path.name}: a bar has high < low", stage="parity")
    return ChartData(name=path.name, sha256=sha, ts=ts, **cols)


# --------------------------------------------------------------------------------------
# Trade list
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class TradeRow:
    """One row of a Strategy Tester "List of trades" export."""

    trade: int
    kind: str  # "entry" | "exit"
    direction: int  # +1 long, -1 short
    signal: str
    when: dt.datetime
    price: float
    quantity: float
    pnl: float | None


@dataclass(frozen=True)
class TradeList:
    name: str
    sha256: str
    rows: tuple[TradeRow, ...]

    def __len__(self) -> int:
        return len(self.rows)

    def trades(self) -> list[tuple[TradeRow, TradeRow]]:
        """``(entry, exit)`` per trade number; an unpaired row is dropped and reported."""
        by_trade: dict[int, dict[str, TradeRow]] = {}
        for row in self.rows:
            by_trade.setdefault(row.trade, {})[row.kind] = row
        return [
            (pair["entry"], pair["exit"])
            for _, pair in sorted(by_trade.items())
            if "entry" in pair and "exit" in pair
        ]

    def open_trades(self) -> list[int]:
        """Trade numbers with an entry but no exit (still open at the export)."""
        by_trade: dict[int, set[str]] = {}
        for row in self.rows:
            by_trade.setdefault(row.trade, set()).add(row.kind)
        return sorted(n for n, kinds in by_trade.items() if "exit" not in kinds)

    def net_profit(self) -> float:
        return float(sum(e.pnl or 0.0 for _, e in self.trades()))

    def covered_range(self) -> tuple[dt.datetime, dt.datetime]:
        """First entry and last exit -- the range the comparison is made over (D-363)."""
        pairs = self.trades()
        if not pairs:
            raise DataError(f"{self.name}: no complete trades", stage="parity")
        return pairs[0][0].when, max(x.when for _, x in pairs)


def _column(header: Any, field: str) -> str:
    names = {str(h).strip().lower().replace("  ", " "): str(h) for h in header}
    for alias in _TRADE_ALIASES[field]:
        if alias in names:
            return names[alias]
    raise DataError(
        f"trade list has no column for {field!r} (tried {_TRADE_ALIASES[field]})", stage="parity"
    )


def _direction_and_kind(type_cell: str) -> tuple[int, str]:
    """``"Entry long"`` / ``"Exit short"`` -> ``(+1, "entry")`` / ``(-1, "exit")``."""
    text = type_cell.strip().lower()
    kind = "entry" if "entry" in text else "exit" if "exit" in text else ""
    direction = 1 if "long" in text else -1 if "short" in text else 0
    if not kind or direction == 0:
        raise DataError(f"cannot read the trade type {type_cell!r}", stage="parity")
    return direction, kind


def _parse_when(text: str, tz: dt.tzinfo) -> dt.datetime:
    cleaned = text.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(cleaned, fmt).replace(tzinfo=tz).astimezone(dt.UTC)
        except ValueError:
            continue
    raise DataError(f"cannot read the trade date/time {text!r}", stage="parity")


def _number(text: str) -> float:
    cleaned = re.sub(r"[^\d.eE+-]", "", str(text).replace(chr(0x2212), "-"))  # U+2212 minus
    if not cleaned or cleaned in ("+", "-", "."):
        raise DataError(f"cannot read the number {text!r}", stage="parity")
    return float(cleaned)


def load_trade_list(
    path: Path,
    export_tz: dt.tzinfo = dt.UTC,
    manifest: dict[str, dict[str, Any]] | None = None,
) -> TradeList:
    """Read a Strategy Tester trade-list export.

    ``export_tz`` is the chart's timezone from the parity config (D-348 records it); the rows
    are converted to UTC so they line up with the chart export's UNIX stamps.
    """
    sha = verify(path, manifest)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise DataError(f"{path.name}: no rows", stage="parity")
    header = list(rows[0])
    cols = {f: _column(header, f) for f in ("trade", "type", "datetime", "price", "quantity")}
    signal_col = _column(header, "signal") if _has(header, "signal") else None
    pnl_col = _column(header, "pnl") if _has(header, "pnl") else None
    out: list[TradeRow] = []
    for row in rows:
        direction, kind = _direction_and_kind(row[cols["type"]])
        out.append(
            TradeRow(
                trade=int(_number(row[cols["trade"]])),
                kind=kind,
                direction=direction,
                signal=(row.get(signal_col, "") if signal_col else "").strip(),
                when=_parse_when(row[cols["datetime"]], export_tz),
                price=_number(row[cols["price"]]),
                quantity=_number(row[cols["quantity"]]),
                pnl=_number(row[pnl_col]) if pnl_col and row.get(pnl_col, "").strip() else None,
            )
        )
    out.sort(key=lambda r: (r.trade, r.kind == "exit"))
    return TradeList(name=path.name, sha256=sha, rows=tuple(out))


def _has(header: list[str], field: str) -> bool:
    names = {str(h).strip().lower() for h in header}
    return any(alias in names for alias in _TRADE_ALIASES[field])
