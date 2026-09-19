"""Dukascopy bid + ask raw months -> canonical mid bars with spread (F-0.1.3).

* ``ts`` = bar start, UTC (the tool writes epoch milliseconds; a non-zero ``utc_offset_minutes``
  recorded in the manifest is subtracted, so the stored time is always UTC).
* bid and ask are joined on ``ts``. Bars present on one side only are dropped and counted;
  more than ``max_one_sided_share`` of all bars is a critical :class:`DataError`.
* ``open/high/low/close`` = (bid + ask) / 2 per field. **The mid high/low is an
  approximation**: the bid high and the ask high need not occur at the same instant, so
  (bid_high + ask_high) / 2 can differ from the true highest mid price of the bar.
* ``spread`` = ask_close - bid_close; any negative spread is critical.
* ``volume`` = bid-side volume (Dukascopy's own volume; ``volume_quality="partial"``).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.core.errors import DataError
from strategy_factory.data.config import DukascopyConfig
from strategy_factory.data.hashing import file_sha256
from strategy_factory.data.schema import RawRef, SeriesMetadata

SERIES_TIMEFRAME = {"h1": "1H", "m1": "1m"}
MID_NOTE = (
    "Dukascopy mid = (bid + ask) / 2 per OHLC field; mid high/low are approximations "
    "(bid and ask extremes need not coincide); spread = ask_close - bid_close; "
    "volume = Dukascopy bid-side volume."
)


def _manifest(p: Path) -> dict[str, Any]:
    m = p.with_name(p.name + ".manifest.json")
    return json.loads(m.read_text(encoding="utf-8")) if m.is_file() else {}


def read_side(paths: list[Path]) -> pl.DataFrame:
    """Concatenate month files of one side; ts corrected to UTC with the manifest offset."""
    frames = []
    for p in paths:
        offset = int(_manifest(p).get("utc_offset_minutes", 0))
        df = pl.read_csv(p, schema_overrides={"timestamp": pl.Int64})  # gzip is detected
        if df.height == 0:
            continue
        frames.append(
            df.select(
                (pl.from_epoch(pl.col("timestamp"), time_unit="ms") - pl.duration(minutes=offset))
                .dt.cast_time_unit("us")
                .dt.replace_time_zone("UTC")
                .alias("ts"),
                *[pl.col(c).cast(pl.Float64) for c in ("open", "high", "low", "close", "volume")],
            )
        )
    if not frames:
        return pl.DataFrame(
            schema={
                "ts": pl.Datetime("us", "UTC"),
                **{c: pl.Float64 for c in ("open", "high", "low", "close", "volume")},
            }
        )
    return pl.concat(frames).unique(subset="ts", keep="first", maintain_order=True).sort("ts")


class DukascopyAdapter:
    """``Adapter`` implementation for Dukascopy bid/ask months."""

    def __init__(self, config: DukascopyConfig | None = None) -> None:
        self.config = config or DukascopyConfig()

    def to_canonical(
        self, raw_paths: list[Path], **params: Any
    ) -> tuple[pl.DataFrame, SeriesMetadata]:
        series: str = params.get("series", "h1")
        symbol: str = params["symbol"]
        instrument: str = params["instrument"]
        asset_class: str = params["asset_class"]
        bid_paths = [p for p in raw_paths if p.parent.name == "bid"]
        ask_paths = [p for p in raw_paths if p.parent.name == "ask"]
        bid, ask = read_side(bid_paths), read_side(ask_paths)
        joined = bid.join(ask, on="ts", how="full", suffix="_ask", coalesce=True)
        one_sided = joined.filter(pl.col("close").is_null() | pl.col("close_ask").is_null()).height
        total = joined.height
        if total and one_sided / total > self.config.max_one_sided_share:
            raise DataError(
                f"{one_sided} of {total} bars ({one_sided / total:.4%}) exist on one side only "
                f"(limit {self.config.max_one_sided_share:.2%})",
                stage="adapter:dukascopy",
                symbol=symbol,
            )
        both = joined.drop_nulls(["close", "close_ask"]).sort("ts")
        spread = pl.col("close_ask") - pl.col("close")
        negative = both.filter(spread < 0).height
        if negative:
            raise DataError(
                f"{negative} bars with negative spread (ask < bid)",
                stage="adapter:dukascopy",
                symbol=symbol,
            )
        bars = both.select(
            "ts",
            *[
                ((pl.col(c) + pl.col(f"{c}_ask")) / 2).alias(c)
                for c in ("open", "high", "low", "close")
            ],
            pl.col("volume"),
            spread.alias("spread"),
        )
        manifests = [_manifest(p) for p in raw_paths]
        stamps = [
            dt.datetime.fromisoformat(m["downloaded_at"])
            for m in manifests
            if m.get("downloaded_at")
        ]
        tool = sorted({m.get("tool", "") for m in manifests} - {""})
        notes = (
            MID_NOTE
            + f" One-sided bars dropped: {one_sided}."
            + (f" Tool: {', '.join(tool)}." if tool else "")
        )
        meta = SeriesMetadata(
            source="dukascopy",
            source_symbol=instrument,
            symbol=symbol,
            asset_class=asset_class,
            timeframe=SERIES_TIMEFRAME[series],
            price_type="mid",
            adjustment="raw",
            session="24x5",
            feed="none",
            volume_quality="partial",
            original_tz="UTC",
            bar_label="start",
            raw_refs=tuple(RawRef(path=p.as_posix(), sha256=file_sha256(p)) for p in raw_paths),
            downloaded_at=max(stamps).astimezone(dt.UTC) if stamps else None,
            notes=notes,
        )
        return bars, meta
