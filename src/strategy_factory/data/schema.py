"""Canonical bar schema, series metadata and bar validation (F-0.1.1).

Every adapter converts a source into this one layout:

* required: ``ts`` (bar **start**, ``Datetime("us", "UTC")``), ``open, high, low, close,
  volume`` (``Float64``);
* optional: ``vwap`` (``Float64``), ``trades`` (``Int64``), ``spread`` (``Float64``).

Daily bars are stamped at the session date 00:00 UTC. :func:`validate_bars` reports issues
instead of raising; the snapshot store refuses frames with any ``critical`` issue.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, field_validator

REQUIRED_COLUMNS: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "open": pl.Float64(),
    "high": pl.Float64(),
    "low": pl.Float64(),
    "close": pl.Float64(),
    "volume": pl.Float64(),
}
OPTIONAL_COLUMNS: dict[str, pl.DataType] = {
    "vwap": pl.Float64(),
    "trades": pl.Int64(),
    "spread": pl.Float64(),
}
CANONICAL_ORDER: tuple[str, ...] = (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS)
PRICE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")

PriceType = Literal["trade", "bid", "ask", "mid"]
Adjustment = Literal["raw", "split", "all", "back_adjusted", "unknown"]
Session = Literal["RTH", "RTH_hour_aligned", "ETH", "24x5", "24x7", "exchange"]
Feed = Literal["sip", "iex", "none"]
VolumeQuality = Literal["full", "partial", "none"]
BarLabel = Literal["start", "end"]
Severity = Literal["critical", "warning", "info"]
TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "1H", "4H", "1D")


def _require_utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() != dt.timedelta(0):
        raise ValueError("datetime must be timezone-aware UTC")
    return value


class RawRef(BaseModel):
    """A raw source file a snapshot was built from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SeriesMetadata(BaseModel):
    """Metadata of one bar series; store fields are filled by the snapshot store."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1)
    source_symbol: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    asset_class: str = Field(min_length=1)
    timeframe: str
    price_type: PriceType
    adjustment: Adjustment
    session: Session
    feed: Feed
    volume_quality: VolumeQuality
    original_tz: str = Field(min_length=1)
    bar_label: BarLabel
    raw_refs: tuple[RawRef, ...] = ()
    downloaded_at: dt.datetime | None = None
    notes: str = ""
    # filled by the store
    snapshot_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    row_count: int | None = Field(default=None, ge=0)
    first_ts: dt.datetime | None = None
    last_ts: dt.datetime | None = None
    created_at: dt.datetime | None = None

    @field_validator("timeframe")
    @classmethod
    def _timeframe(cls, value: str) -> str:
        if value not in TIMEFRAMES:
            raise ValueError(f"timeframe must be one of {TIMEFRAMES}, got {value!r}")
        return value

    @field_validator("downloaded_at", "first_ts", "last_ts", "created_at")
    @classmethod
    def _utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _require_utc(value)

    @property
    def is_stored(self) -> bool:
        return self.snapshot_hash is not None


class ValidationIssue(BaseModel):
    """One problem found in a bar frame."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    severity: Severity
    message: str
    count: int = 0


def _dtype_ok(df: pl.DataFrame, col: str, expected: pl.DataType) -> bool:
    return col in df.columns and df.schema[col] == expected


def validate_bars(df: pl.DataFrame, meta: SeriesMetadata) -> list[ValidationIssue]:
    """Check ``df`` against the canonical schema; returns issues (never raises).

    Value checks run only on columns whose dtype is correct, so one wrong dtype yields one
    issue instead of a cascade. Non-positive prices are allowed only for
    ``adjustment == "back_adjusted"``.
    """
    issues: list[ValidationIssue] = []

    def add(code: str, message: str, count: int = 0, severity: Severity = "critical") -> None:
        issues.append(ValidationIssue(code=code, severity=severity, message=message, count=count))

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        add("missing_column", f"missing required columns: {missing}", len(missing))
    known = set(CANONICAL_ORDER)
    extra = [c for c in df.columns if c not in known]
    if extra:
        add("extra_column", f"columns not in the canonical schema: {extra}", len(extra))

    expected_all = {**REQUIRED_COLUMNS, **OPTIONAL_COLUMNS}
    for col in df.columns:
        if col not in expected_all or col == "ts":
            continue
        if df.schema[col] != expected_all[col]:
            add(
                "wrong_dtype",
                f"column {col!r} has dtype {df.schema[col]}, expected {expected_all[col]}",
            )

    ts_ok = False
    if "ts" in df.columns:
        ts_type = df.schema["ts"]
        if not isinstance(ts_type, pl.Datetime):
            add("wrong_dtype", f"column 'ts' has dtype {ts_type}, expected Datetime(us, UTC)")
        elif ts_type.time_zone is None:
            add("ts_naive", "column 'ts' is timezone-naive; must be UTC")
        elif ts_type.time_zone != "UTC":
            add("ts_not_utc", f"column 'ts' has time zone {ts_type.time_zone!r}; must be UTC")
        elif ts_type.time_unit != "us":
            add("wrong_dtype", f"column 'ts' has time unit {ts_type.time_unit!r}, expected 'us'")
        else:
            ts_ok = True

    if ts_ok and df.height:
        ts = df["ts"]
        nulls = ts.null_count()
        if nulls:
            add("nan_in_required", "column 'ts' contains nulls", nulls)
        diffs = ts.drop_nulls().diff().drop_nulls()
        backwards = int((diffs < dt.timedelta(0)).sum())
        if backwards:
            add("ts_not_monotonic", "timestamps are not sorted ascending", backwards)
        dups = df.height - nulls - ts.drop_nulls().n_unique()
        if dups:
            add("ts_duplicate", "duplicate timestamps", dups)

    ok_num = [c for c in (*PRICE_COLUMNS, "volume") if _dtype_ok(df, c, pl.Float64())]
    if df.height:
        for col in ok_num:
            bad = int(df.select((pl.col(col).is_null() | pl.col(col).is_nan()).sum()).item())
            if bad:
                add("nan_in_required", f"column {col!r} contains NaN/null", bad)

    if df.height and all(c in ok_num for c in PRICE_COLUMNS):
        o, h, lo, c = (df[x] for x in PRICE_COLUMNS)
        n = int((h < lo).sum())
        if n:
            add("high_lt_low", "high < low", n)
        n = int(((o > h) | (o < lo) | (c > h) | (c < lo)).sum())
        if n:
            add("ohlc_outside_range", "open or close outside [low, high]", n)
        if meta.adjustment != "back_adjusted":
            n = int(((o <= 0) | (h <= 0) | (lo <= 0) | (c <= 0)).sum())
            if n:
                add(
                    "nonpositive_price",
                    "non-positive prices (allowed only for back_adjusted, "
                    f"got {meta.adjustment!r})",
                    n,
                )
    return issues


def critical_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.severity == "critical"]


def canonical_columns(df: pl.DataFrame) -> list[str]:
    """Canonical column order restricted to the columns present in ``df``."""
    return [c for c in CANONICAL_ORDER if c in df.columns]


__all__ = [
    "CANONICAL_ORDER",
    "OPTIONAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "TIMEFRAMES",
    "Adjustment",
    "BarLabel",
    "Feed",
    "PriceType",
    "RawRef",
    "SeriesMetadata",
    "Session",
    "ValidationIssue",
    "VolumeQuality",
    "canonical_columns",
    "critical_issues",
    "validate_bars",
]
