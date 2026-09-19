"""Small synthetic canonical bar frames and metadata for tests."""

from __future__ import annotations

import datetime as dt
from typing import Any

import polars as pl

from strategy_factory.data.schema import SeriesMetadata

T0 = dt.datetime(2024, 1, 2, tzinfo=dt.UTC)


def make_bars(
    n: int = 5, start: dt.datetime = T0, step: dt.timedelta | None = None
) -> pl.DataFrame:
    """Valid daily bars: rising closes, OHLC consistent, UTC bar-start timestamps."""
    step = step or dt.timedelta(days=1)
    ts = [start + i * step for i in range(n)]
    close = [100.0 + i for i in range(n)]
    return pl.DataFrame(
        {
            "ts": ts,
            "open": [c - 0.5 for c in close],
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [1000.0 + i for i in range(n)],
        },
        schema={
            "ts": pl.Datetime("us", "UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
        },
    )


def make_meta(**overrides: Any) -> SeriesMetadata:
    base: dict[str, Any] = {
        "source": "test",
        "source_symbol": "TEST",
        "symbol": "TEST",
        "asset_class": "us_equity",
        "timeframe": "1D",
        "price_type": "trade",
        "adjustment": "split",
        "session": "RTH",
        "feed": "sip",
        "volume_quality": "full",
        "original_tz": "America/New_York",
        "bar_label": "start",
        "raw_refs": [{"path": "raw/test/TEST.csv", "sha256": "0" * 64}],
        "downloaded_at": T0,
        "notes": "",
    }
    base.update(overrides)
    return SeriesMetadata.model_validate(base)
