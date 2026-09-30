"""Dukascopy bid + ask raw months -> canonical mid bars with spread (F-0.1.3).

* ``ts`` = bar start, UTC (the tool writes epoch milliseconds; a non-zero ``utc_offset_minutes``
  recorded in the manifest is subtracted, so the stored time is always UTC).
* bid and ask are joined on ``ts``. Bars present on one side only are dropped and counted;
  more than ``max_one_sided_share`` of all bars is a critical :class:`DataError`.
* ``open/high/low/close`` = (bid + ask) / 2 per field. **The mid high/low is an
  approximation**: the bid high and the ask high need not occur at the same instant, so
  (bid_high + ask_high) / 2 can differ from the true highest mid price of the bar.
* **D-673:** per side and before the mid, a bar whose open or close lies outside its own high/low
  by at most ``ohlc_repair_max`` has that high or low widened just enough to cover it; an open or
  close is never changed, and a larger excess is left for the store's validation to refuse. The
  repaired bars are counted per side and month in the snapshot notes.
* ``spread`` = ask_close - bid_close; any negative spread is critical.
* ``volume`` = bid-side volume (Dukascopy's own volume; ``volume_quality="partial"``).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, cast, get_args

import polars as pl

from strategy_factory.core.errors import DataError
from strategy_factory.data.config import DukascopyConfig
from strategy_factory.data.hashing import file_sha256
from strategy_factory.data.schema import AssetClass, RawRef, SeriesMetadata

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


#: float slack when comparing an excess with the limit (quotes carry at most 6 decimals)
_REPAIR_SLACK = 1e-9


def repair_ohlc(side: pl.DataFrame, limit: float) -> tuple[pl.DataFrame, dict[str, int]]:
    """D-673: widen ``high`` / ``low`` to cover an ``open`` / ``close`` that lies outside them by at
    most ``limit``; never change an open or close. Returns the side and ``{YYYY-MM: bars}``.

    A bar whose excess is larger is returned unchanged, so the store's bar validation refuses it.
    """
    top = pl.max_horizontal("open", "close")
    bottom = pl.min_horizontal("open", "close")
    over = (top - pl.col("high")).clip(lower_bound=0)
    under = (pl.col("low") - bottom).clip(lower_bound=0)
    fixable = (pl.max_horizontal(over, under) > 0) & (
        pl.max_horizontal(over, under) <= limit + _REPAIR_SLACK
    )
    marked = side.with_columns(fixable.alias("_repair"))
    counts = (
        marked.filter("_repair")
        .group_by(pl.col("ts").dt.strftime("%Y-%m").alias("month"))
        .len()
        .sort("month")
    )
    repaired = marked.with_columns(
        pl.when("_repair").then(pl.max_horizontal("high", top)).otherwise("high").alias("high"),
        pl.when("_repair").then(pl.min_horizontal("low", bottom)).otherwise("low").alias("low"),
    ).drop("_repair")
    return repaired, dict(counts.rows())


def _repair_note(bid: dict[str, int], ask: dict[str, int], limit: float) -> str:
    """The snapshot-notes line for D-673 (empty when nothing was repaired, so the notes of an
    untouched series are exactly as before)."""
    if not bid and not ask:
        return ""
    months = sorted(set(bid) | set(ask))
    per = "; ".join(f"{m}: bid {bid.get(m, 0)}, ask {ask.get(m, 0)}" for m in months)
    total = sum(bid.values()) + sum(ask.values())
    return (
        f" OHLC repair (D-673): {total} side bar(s) with open/close outside high/low by <= "
        f"{limit:g} had high/low widened (prices unchanged) -- {per}."
    )


def as_asset_class(value: str, symbol: str) -> AssetClass:
    """Universe-file asset class -> the fixed enumeration (unknown values are errors)."""
    if value not in get_args(AssetClass):
        raise DataError(
            f"asset class {value!r} is not one of {get_args(AssetClass)}", symbol=symbol
        )
    return cast(AssetClass, value)


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
        asset_class = as_asset_class(params["asset_class"], symbol)
        bid_paths = [p for p in raw_paths if p.parent.name == "bid"]
        ask_paths = [p for p in raw_paths if p.parent.name == "ask"]
        bid, ask = read_side(bid_paths), read_side(ask_paths)
        limit = self.config.ohlc_repair_max
        (bid, bid_fixed), (ask, ask_fixed) = repair_ohlc(bid, limit), repair_ohlc(ask, limit)
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
            + _repair_note(bid_fixed, ask_fixed, limit)
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
