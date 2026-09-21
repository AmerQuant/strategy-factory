"""Raw -> snapshot ingest for Alpaca (T04a): adapter, split check, store, catalog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from strategy_factory.core.errors import DataError
from strategy_factory.core.logging import get_logger
from strategy_factory.data.adapters.alpaca import AlpacaAdapter
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import AlpacaConfig, load_known_splits
from strategy_factory.data.download.alpaca import RAW_SUBDIR, latest_chunks
from strategy_factory.data.download.rawfiles import read_manifest
from strategy_factory.data.split_check import (
    check_splits,
    daily_closes,
    read_crosscheck_csv,
    warning_note,
    write_report,
)
from strategy_factory.data.store import SnapshotStore
from strategy_factory.data.universe import DAILY_RAW_DIR

log = get_logger(__name__)


#: D-397: a known split the feed did not apply poisons every backtest crossing that date, so the
#: symbol is **not** ingested. It is listed in the split-check report and the run continues.
UNADJUSTED = "unadjusted"


@dataclass(frozen=True)
class IngestResult:
    symbol: str
    status: str  # "ingested" | "no_data" | "unadjusted_split" | "failed"
    snapshot_hash: str | None = None
    rows: int = 0
    is_reference: bool = False
    split_warning: str = ""


def crosscheck_file(raw_root: Path, symbol: str) -> Path:
    return (
        raw_root.joinpath(*DAILY_RAW_DIR) / f"us_{symbol.replace('.', '_').replace('/', '_')}.csv"
    )


def raw_symbols(raw_root: Path, timeframe: str) -> list[str]:
    d = raw_root.joinpath(*RAW_SUBDIR, timeframe)
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


def ingest_alpaca_symbol(
    symbol: str,
    timeframe: str,
    raw_root: Path,
    store: SnapshotStore,
    catalog: Catalog,
    config: AlpacaConfig,
    adapter: AlpacaAdapter | None = None,
    set_reference: bool = False,
    pit_symbol: str | None = None,
) -> IngestResult:
    files = latest_chunks(raw_root, timeframe, symbol)
    if not any((read_manifest(f) or {}).get("row_count", 0) for f in files):
        return IngestResult(symbol, "no_data")
    adapter = adapter or AlpacaAdapter(config)
    df, meta = adapter.to_canonical(files, timeframe=timeframe, symbol=symbol)
    if df.height == 0:
        return IngestResult(symbol, "no_data")

    tz = config.hourly_session.timezone if timeframe == "1H" else None
    xfile = crosscheck_file(raw_root, symbol)
    cross = read_crosscheck_csv(xfile) if xfile.is_file() else None
    rows = check_splits(
        symbol,
        timeframe,
        daily_closes(df, tz),
        cross,
        load_known_splits(config.split_check.known_splits_file),
        config.split_check,
    )
    write_report(raw_root / "_reports" / f"alpaca_split_check_{timeframe}.csv", symbol, rows)
    warning = warning_note(rows)
    unadjusted = [r for r in rows if r["verdict"] == UNADJUSTED]
    if unadjusted:
        # D-397: fail this symbol, not the run. AVGO 2024-07-15 is the worked case (T04i section 4).
        dates = ", ".join(str(r["date"]) for r in unadjusted)
        log.error("%s %s: known split unadjusted on %s - not ingested", symbol, timeframe, dates)
        return IngestResult(
            symbol,
            "unadjusted_split",
            split_warning=f"known split unadjusted on {dates}; not ingested (D-397)",
        )
    notes = meta.notes + (
        "" if cross is not None else " No cross-check file (MS-US-1D) for this symbol."
    )
    if pit_symbol and pit_symbol != symbol:
        notes += f" Historical (S&P 500 PIT) ticker: {pit_symbol}; downloaded as {symbol}."
    if warning:
        notes += " " + warning
        log.warning("%s %s: %s", symbol, timeframe, warning)
    stored = store.write_snapshot(df, meta.model_copy(update={"notes": notes.strip()}))
    catalog.register(stored)
    if stored.snapshot_hash is None:
        raise DataError("store returned metadata without snapshot hash", symbol=symbol)
    make_ref = set_reference or not catalog.has_reference(symbol, timeframe)
    if make_ref:
        catalog.set_reference(symbol, timeframe, stored.snapshot_hash, note="alpaca ingest")
    return IngestResult(
        symbol, "ingested", stored.snapshot_hash, stored.row_count or 0, make_ref, warning
    )
