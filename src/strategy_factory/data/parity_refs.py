"""TradingView parity references (T11 §1, D-348): read-only, verified, used **as exported**.

Three kinds of file live in ``SFAC_RAW_ROOT/reference/tradingview/parity/``:

* **chart data** -- a TradingView "Export chart data" CSV, ``time,open,high,low,close`` with
  ``time`` in UNIX seconds. The stamp is the **bar open in UTC**; a SPY daily bar is stamped
  14:30 UTC (09:30 New York), not 00:00 UTC.
* **strategy report** -- the Strategy Tester ``.xlsx`` export, whose ``Trades`` sheet is the
  trade list and whose ``Properties`` sheet records the settings the run used. It is read with
  **openpyxl, imported lazily** (D-317): parity runs only in tests and ``selftest``, so the
  runtime never needs an Excel reader. A plain CSV trade list is read too.
* **Pine source** -- the ``.pine`` file. :func:`pine_settings_from_source` reads the
  ``strategy()`` call, and :func:`cross_check_properties` compares it with the ``Properties``
  sheet so a disagreement is reported rather than silently resolved.

**The bars are used exactly as exported** (D-348): no D-010 Sunday merge, no resampling, no
re-bucketing to 00:00 UTC, no Alpaca or Dukascopy bars. A parity run is a comparison against
TradingView, so anything we "fix" first would be the thing we are trying to measure.

**Provenance (as in D-340).** ``manifest.json`` next to the files lists every file with its
SHA-256 and row count; :func:`load_chart_data` and :func:`load_trade_list` **verify the hash on
every load** and raise when it differs or the manifest is missing. The folder is never written
to (CLAUDE.md rule 11): ``scripts/write_parity_manifest.ps1`` is run by the user (D-031).

The references are **not snapshots**: they never enter the catalog, the snapshot store or
``SFAC_DATA_ROOT``. This module lives in ``selftest`` because ``data/`` is stream B's
(D-357).

**Times in a strategy report are in the chart's timezone**, not UTC: for both D-348
references that is ``America/New_York`` (verified -- the XAUUSD trade stamped 03:00 fills at
the 08:00 UTC bar whose open is exactly the exported price). The timezone comes from the
parity config, which records it as D-348 requires.
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
    "trade": ("trade #", "trade number", "trade"),
    "type": ("type",),
    "signal": ("signal", "signal name"),
    "datetime": ("date/time", "date and time", "date time", "datetime"),
    "price": ("price usd", "price", "price (usd)"),
    "quantity": ("size (qty)", "contracts", "quantity", "position size"),
    "pnl": ("net pnl usd", "profit usd", "profit (usd)", "p&l usd", "net profit usd"),
    "cumulative": ("cumulative pnl usd", "cumulative profit usd", "cum. profit usd"),
}


# --------------------------------------------------------------------------------------
# Repo fixtures (D-359): the gate runs in CI, where there is no raw store
# --------------------------------------------------------------------------------------
#: Byte-identical copies of the six references, so the D-011 gate is **never skipped**
#: (CLAUDE.md rule 9). The raw store stays the source of truth: a test asserts every hash
#: against the raw ``manifest.json`` whenever ``SFAC_RAW_ROOT`` is present.
FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "parity"


def fixture_dir() -> Path:
    if not FIXTURE_DIR.is_dir():  # pragma: no cover - the fixtures are committed
        raise ConfigError(f"parity fixtures not found at {FIXTURE_DIR}")
    return FIXTURE_DIR


def fixture(name: str) -> Path:
    """One parity fixture by file name; its hash is checked when it is loaded."""
    path = fixture_dir() / name
    if not path.is_file():
        available = sorted(p.name for p in fixture_dir().iterdir() if p.name != MANIFEST)
        raise ConfigError(f"parity fixture {name!r} not found; have {available}")
    return path


def raw_dir() -> Path | None:
    """The raw parity folder, or ``None`` when ``SFAC_RAW_ROOT`` is not set (CI)."""
    from strategy_factory.data.download.rawfiles import raw_root

    try:
        folder = raw_root() / PARITY_DIR
    except ConfigError:
        return None
    return folder if folder.is_dir() else None


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

    def index_on_date(self, when: dt.datetime) -> int:
        """Index of the bar whose **UTC date** is ``when``'s date.

        A daily trade row carries no time of day (TradingView writes ``1993-02-19``), while
        the bar is stamped at the session open (14:30 UTC for BATS:SPY). Matching on the date
        is how a daily reference lines up; an intraday one uses :meth:`index_of`.
        """
        target = when.astimezone(dt.UTC).date()
        days = self.ts.astype("datetime64[s]").astype("datetime64[D]")
        hits = np.flatnonzero(days == np.datetime64(target))
        if hits.size != 1:
            raise DataError(
                f"{self.name}: {target.isoformat()} matches {hits.size} bars, expected 1",
                stage="parity",
            )
        return int(hits[0])

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


_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _number(text: str) -> float:
    """The first number in ``text``; ``"0 orders"``, ``"0 ticks"`` and ``"1,234.5"`` all work."""
    match = _NUMBER.search(str(text).replace(chr(0x2212), "-"))  # U+2212 minus
    if match is None:
        raise DataError(f"cannot read the number {text!r}", stage="parity")
    return float(match.group().replace(",", ""))


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


# --------------------------------------------------------------------------------------
# Strategy report (.xlsx): the Trades and Properties sheets
# --------------------------------------------------------------------------------------
TRADES_SHEET = "Trades"
PROPERTIES_SHEET = "Properties"
#: Cells TradingView writes for a position that is still open at the end of the report.
_OPEN_MARKERS = ("open", chr(0x2014), chr(0x2013), "-", "")  # em dash, en dash


def _load_workbook(path: Path) -> Any:
    """openpyxl, imported lazily (D-317): the runtime never needs an Excel reader."""
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - openpyxl is a dev dependency
        raise ConfigError(
            "reading a TradingView strategy report needs openpyxl (a dev dependency, D-317)"
        ) from exc
    try:
        return openpyxl.load_workbook(path, read_only=True, data_only=True)
    except (OSError, KeyError, ValueError) as exc:
        raise DataError(f"{path.name}: cannot open the workbook: {exc}", stage="parity") from exc


def _sheet_rows(book: Any, sheet: str, path: Path) -> tuple[list[str], list[tuple[Any, ...]]]:
    if sheet not in book.sheetnames:
        raise DataError(
            f"{path.name}: no {sheet!r} sheet (found {book.sheetnames})", stage="parity"
        )
    rows = list(book[sheet].iter_rows(values_only=True))
    if not rows:
        raise DataError(f"{path.name}: sheet {sheet!r} is empty", stage="parity")
    header = ["" if c is None else str(c).strip() for c in rows[0]]
    return header, rows[1:]


def load_properties(
    path: Path, manifest: dict[str, dict[str, Any]] | None = None
) -> dict[str, str]:
    """The ``Properties`` sheet as ``{name: value}``; a report without one gives ``{}``."""
    verify(path, manifest)
    book = _load_workbook(path)
    try:
        if PROPERTIES_SHEET not in book.sheetnames:
            return {}
        _, rows = _sheet_rows(book, PROPERTIES_SHEET, path)
        return {
            str(r[0]).strip(): str(r[1]).strip()
            for r in rows
            if r and r[0] is not None and len(r) > 1 and r[1] is not None
        }
    finally:
        book.close()


def _is_open_cell(value: Any) -> bool:
    return value is None or str(value).strip().lower() in _OPEN_MARKERS


def load_strategy_report(
    path: Path,
    export_tz: dt.tzinfo = dt.UTC,
    manifest: dict[str, dict[str, Any]] | None = None,
) -> TradeList:
    """The ``Trades`` sheet of a Strategy Tester ``.xlsx`` export.

    TradingView writes one row per leg, **exit before entry** within a trade. A position still
    open at the end has an exit row whose date and price are placeholders; that row is dropped,
    so the trade shows up in :meth:`TradeList.open_trades` and never in a comparison.
    """
    sha = verify(path, manifest)
    book = _load_workbook(path)
    try:
        header, rows = _sheet_rows(book, TRADES_SHEET, path)
    finally:
        book.close()
    fields = ("trade", "type", "datetime", "price", "quantity")
    cols = {f: header.index(_column(header, f)) for f in fields}
    signal_i = header.index(_column(header, "signal")) if _has(header, "signal") else None
    pnl_i = header.index(_column(header, "pnl")) if _has(header, "pnl") else None
    out: list[TradeRow] = []
    for row in rows:
        if not row or row[cols["trade"]] is None:
            continue
        direction, kind = _direction_and_kind(str(row[cols["type"]]))
        when_cell, price_cell = row[cols["datetime"]], row[cols["price"]]
        if _is_open_cell(when_cell) or _is_open_cell(price_cell):
            continue  # still open at the end of the report
        when = (
            when_cell.replace(tzinfo=export_tz).astimezone(dt.UTC)
            if isinstance(when_cell, dt.datetime)
            else _parse_when(str(when_cell), export_tz)
        )
        signal = "" if signal_i is None or row[signal_i] is None else str(row[signal_i]).strip()
        pnl = (
            _number(str(row[pnl_i]))
            if pnl_i is not None and not _is_open_cell(row[pnl_i])
            else None
        )
        out.append(
            TradeRow(
                trade=int(_number(str(row[cols["trade"]]))),
                kind=kind,
                direction=direction,
                signal=signal,
                when=when,
                price=_number(str(price_cell)),
                quantity=_number(str(row[cols["quantity"]])),
                pnl=pnl,
            )
        )
    if not out:
        raise DataError(f"{path.name}: the {TRADES_SHEET!r} sheet has no trades", stage="parity")
    out.sort(key=lambda r: (r.trade, r.kind == "exit"))
    return TradeList(name=path.name, sha256=sha, rows=tuple(out))


# --------------------------------------------------------------------------------------
# Pine source: the strategy() call
# --------------------------------------------------------------------------------------
_STRATEGY_CALL = re.compile(r"\bstrategy\s*\((?P<body>.*?)\)\s*(?:\n|$)", re.DOTALL)
#: ``strategy()`` argument -> the ``PineSettings`` field it fills.
_PINE_FIELDS = {
    "initial_capital": "initial_capital",
    "default_qty_value": "qty_value",
    "commission_value": "commission_value",
    "slippage": "slippage_ticks",
    "pyramiding": "pyramiding",
    "process_orders_on_close": "process_orders_on_close",
    "calc_on_every_tick": "calc_on_every_tick",
    "use_bar_magnifier": "bar_magnifier",
}
_QTY_TYPES = {
    "strategy.cash": "cash_amount",
    "strategy.percent_of_equity": "percent_of_equity",
    "strategy.fixed": "fixed_contracts",
}
_COMMISSION_TYPES = {
    "strategy.commission.percent": "percent",
    "strategy.commission.cash_per_contract": "per_contract",
    "strategy.commission.cash_per_order": "per_order",
}
_BOOL_FIELDS = ("process_orders_on_close", "calc_on_every_tick", "bar_magnifier")
_INT_FIELDS = ("slippage_ticks", "pyramiding")


def _strategy_body(source: str) -> str:
    match = _STRATEGY_CALL.search(source)
    if match is None:
        raise DataError("the Pine source has no strategy(...) call", stage="parity")
    return match.group("body")


def _pine_args(body: str) -> dict[str, str]:
    """The ``name = value`` pairs of the ``strategy()`` call, comments stripped."""
    text = re.sub(r"//[^\n]*", "", body)
    args: dict[str, str] = {}
    for part in text.split(","):
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        args[name.strip()] = value.strip()
    return args


def pine_settings_from_source(source: str, tick_size: float, atr_length: int) -> dict[str, Any]:
    """The ``pine`` block of a parity config, read from the ``strategy()`` call.

    ``tick_size`` and ``atr_length`` are not arguments of ``strategy()``: the tick size belongs
    to the symbol (the ``Properties`` sheet states it) and the ATR length is a script input, so
    both are passed in and cross-checked against the report.
    """
    args = _pine_args(_strategy_body(source))
    out: dict[str, Any] = {"atr_length": int(atr_length), "tick_size": float(tick_size)}
    for arg, field in _PINE_FIELDS.items():
        if arg not in args:
            continue
        raw = args[arg]
        if field in _BOOL_FIELDS:
            out[field] = raw.lower() == "true"
        elif field in _INT_FIELDS:
            out[field] = int(float(raw))
        else:
            out[field] = float(raw)
    qty = args.get("default_qty_type", "")
    if qty:
        if qty not in _QTY_TYPES:
            raise DataError(f"unknown default_qty_type {qty!r}", stage="parity")
        out["qty_type"] = _QTY_TYPES[qty]
    comm = args.get("commission_type", "")
    if comm:
        if comm not in _COMMISSION_TYPES:
            raise DataError(f"unknown commission_type {comm!r}", stage="parity")
        out["commission_type"] = _COMMISSION_TYPES[comm]
    out["fill_assumptions"] = (
        "strategy(): fill_orders_on_standard_ohlc = "
        f"{args.get('fill_orders_on_standard_ohlc', 'unset')}, calc_on_order_fills = "
        f"{args.get('calc_on_order_fills', 'unset')}, margin_long = "
        f"{args.get('margin_long', 'unset')}, margin_short = "
        f"{args.get('margin_short', 'unset')}"
    )
    return out


def cross_check_properties(pine: dict[str, Any], properties: dict[str, str]) -> list[str]:
    """Disagreements between the ``strategy()`` call and the ``Properties`` sheet.

    An empty list means the two agree (or the sheet does not state the value). Every entry is
    **reported**, never silently resolved: the Pine source is the definition, the sheet is the
    evidence of what actually ran.
    """
    if not properties:
        return []
    problems: list[str] = []

    def compare(label: str, field: str, parse: Any) -> None:
        if label not in properties or field not in pine:
            return
        try:
            reported = parse(properties[label])
        except (TypeError, ValueError):
            problems.append(f"{label}: cannot read the reported value {properties[label]!r}")
            return
        if reported != pine[field]:
            problems.append(
                f"{label}: the report says {reported!r}, strategy() says {pine[field]!r}"
            )

    compare("Initial capital", "initial_capital", float)
    compare("Default order size", "qty_value", float)
    compare("Commission", "commission_value", float)
    compare("Tick size", "tick_size", float)
    compare("Slippage", "slippage_ticks", lambda v: int(_number(v)))
    compare("Pyramiding", "pyramiding", lambda v: int(_number(v)))
    magnifier = properties.get("Bar detalization", "")
    if magnifier and "bar_magnifier" in pine:
        reported_on = "default" not in magnifier.lower()
        if reported_on != bool(pine["bar_magnifier"]):
            problems.append(
                f"Bar detalization: the report says {magnifier!r}, strategy() says "
                f"use_bar_magnifier = {pine['bar_magnifier']}"
            )
    execution = properties.get("Script execution", "")
    if execution and "calc_on_every_tick" in pine:
        reported_tick = "tick" in execution.lower() and "bar close" not in execution.lower()
        if reported_tick != bool(pine["calc_on_every_tick"]):
            problems.append(
                f"Script execution: the report says {execution!r}, strategy() says "
                f"calc_on_every_tick = {pine['calc_on_every_tick']}"
            )
    return problems
