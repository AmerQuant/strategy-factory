"""Yahoo daily raw frame -> canonical daily bars (F-0.1.4).

* ``ts`` = session date (from Yahoo's ``Date``, which is midnight in the exchange time zone)
  at 00:00 UTC.
* Prices are **raw** (downloaded with ``auto_adjust=False``); ``Close`` is used, never
  ``Adj Close``.
* ``volume``: Yahoo reports 0 for indices without real volume -> ``volume_quality="none"``
  (all zero); otherwise ``partial``. Missing volume becomes 0.
* The close-time metadata of the series (``close_time_local``, ``close_tz``,
  ``close_time_status``) is carried in ``notes`` until the catalog gets dedicated fields;
  it is needed for leakage-safe as-of joins (spec addendum section 5.3).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import polars as pl

from strategy_factory.core.errors import DataError
from strategy_factory.data.hashing import file_sha256
from strategy_factory.data.schema import RawRef, SeriesMetadata, VolumeQuality


def close_time_note(close_time_local: str, close_tz: str, status: str) -> str:
    return (
        f"close_time_local={close_time_local or 'unknown'}; close_tz={close_tz or 'unknown'}; "
        f"close_time_status={status or 'to_verify'}"
    )


class YahooAdapter:
    """``Adapter`` implementation for one Yahoo raw file (the latest version)."""

    def to_canonical(
        self, raw_paths: list[Path], **params: Any
    ) -> tuple[pl.DataFrame, SeriesMetadata]:
        if len(raw_paths) != 1:
            raise DataError("the Yahoo adapter takes exactly one raw version")
        path = raw_paths[0]
        ticker: str = params["ticker"]
        symbol: str = params["symbol"]
        raw = pl.read_parquet(path)
        if "Date" not in raw.columns or "Close" not in raw.columns:
            raise DataError(f"unexpected Yahoo columns {raw.columns}", symbol=symbol)
        date_type = raw.schema["Date"]
        tz = date_type.time_zone if isinstance(date_type, pl.Datetime) else None
        session = pl.col("Date").dt.date() if tz else pl.col("Date").cast(pl.Date)
        volume = (
            pl.col("Volume").cast(pl.Float64).fill_null(0.0)
            if "Volume" in raw.columns
            else pl.lit(0.0)
        )
        bars = (
            raw.select(
                session.cast(pl.Datetime("us")).dt.replace_time_zone("UTC").alias("ts"),
                *[
                    pl.col(c).cast(pl.Float64).alias(c.lower())
                    for c in ("Open", "High", "Low", "Close")
                ],
                volume.alias("volume"),
            )
            .drop_nulls(["open", "high", "low", "close"])
            .sort("ts")
        )
        if bars["ts"].n_unique() != bars.height:
            raise DataError("duplicate session dates in the Yahoo frame", symbol=symbol)
        vq: VolumeQuality = "none" if bars.height and (bars["volume"] == 0).all() else "partial"
        manifest_file = path.with_name(path.name + ".manifest.json")
        manifest = (
            json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.is_file() else {}
        )
        downloaded = manifest.get("downloaded_at")
        notes = close_time_note(
            params.get("close_time_local", ""),
            params.get("close_tz", ""),
            params.get("close_time_status", ""),
        )
        if manifest.get("client"):
            notes += f"; {manifest['client']}, auto_adjust=False, actions=False"
        meta = SeriesMetadata(
            source="yahoo",
            source_symbol=ticker,
            symbol=symbol,
            asset_class="aux_index",
            timeframe="1D",
            price_type="trade",
            adjustment="raw",
            session="exchange",
            feed="none",
            volume_quality=vq,
            original_tz=tz or "unknown",
            bar_label="start",
            raw_refs=(RawRef(path=path.as_posix(), sha256=file_sha256(path)),),
            downloaded_at=dt.datetime.fromisoformat(downloaded).astimezone(dt.UTC)
            if downloaded
            else None,
            notes=notes,
        )
        return bars, meta
