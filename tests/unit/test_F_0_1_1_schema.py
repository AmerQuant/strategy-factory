"""F-0.1.1: canonical bar schema, metadata validation and bar validation."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest
from fixtures.bars import make_bars, make_meta
from pydantic import ValidationError

from strategy_factory.data.adapters.base import Adapter
from strategy_factory.data.schema import (
    CANONICAL_ORDER,
    SeriesMetadata,
    critical_issues,
    validate_bars,
)


def codes(df: pl.DataFrame, **meta_overrides: object) -> set[str]:
    return {i.code for i in validate_bars(df, make_meta(**meta_overrides))}


def test_F_0_1_1_valid_frame_has_no_issues() -> None:
    assert validate_bars(make_bars(), make_meta()) == []


def test_F_0_1_1_valid_frame_with_optional_columns() -> None:
    df = make_bars(3).with_columns(
        pl.lit(100.0).alias("vwap"),
        pl.lit(12, dtype=pl.Int64).alias("trades"),
        pl.lit(0.1).alias("spread"),
    )
    assert validate_bars(df, make_meta()) == []


def test_F_0_1_1_canonical_order() -> None:
    assert CANONICAL_ORDER == (
        "ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "vwap",
        "trades",
        "spread",
    )


# -- one test per issue ------------------------------------------------------------------
def test_F_0_1_1_missing_column() -> None:
    assert codes(make_bars().drop("volume")) == {"missing_column"}


def test_F_0_1_1_extra_column() -> None:
    assert codes(make_bars().with_columns(pl.lit(1.0).alias("foo"))) == {"extra_column"}


def test_F_0_1_1_wrong_dtype_price() -> None:
    assert codes(make_bars().with_columns(pl.col("close").cast(pl.Float32))) == {"wrong_dtype"}


def test_F_0_1_1_wrong_dtype_optional() -> None:
    assert codes(make_bars().with_columns(pl.lit(3.0).alias("trades"))) == {"wrong_dtype"}


def test_F_0_1_1_wrong_ts_time_unit() -> None:
    df = make_bars().with_columns(pl.col("ts").dt.cast_time_unit("ns"))
    assert codes(df) == {"wrong_dtype"}


def test_F_0_1_1_naive_ts() -> None:
    df = make_bars().with_columns(pl.col("ts").dt.replace_time_zone(None))
    assert codes(df) == {"ts_naive"}


def test_F_0_1_1_non_utc_ts() -> None:
    df = make_bars().with_columns(pl.col("ts").dt.convert_time_zone("America/New_York"))
    assert codes(df) == {"ts_not_utc"}


def test_F_0_1_1_non_monotonic_ts() -> None:
    df = make_bars()
    df = pl.concat([df.slice(2), df.slice(0, 2)])
    assert codes(df) == {"ts_not_monotonic"}


def test_F_0_1_1_duplicate_ts() -> None:
    df = make_bars()
    df = pl.concat([df, df.slice(4, 1)])
    assert codes(df) == {"ts_duplicate"}


def test_F_0_1_1_high_below_low() -> None:
    df = make_bars().with_columns(
        pl.when(pl.int_range(pl.len()) == 1).then(90.0).otherwise(pl.col("high")).alias("high")
    )
    assert "high_lt_low" in codes(df)


def test_F_0_1_1_ohlc_outside_range() -> None:
    df = make_bars().with_columns((pl.col("high") + 5).alias("close"))
    assert codes(df) == {"ohlc_outside_range"}


def test_F_0_1_1_nonpositive_price_rejected() -> None:
    df = make_bars().with_columns(pl.col(c) - 200.0 for c in ("open", "high", "low", "close"))
    assert codes(df, adjustment="split") == {"nonpositive_price"}
    assert codes(df, adjustment="raw") == {"nonpositive_price"}


def test_F_0_1_1_back_adjusted_allows_negative_prices() -> None:
    df = make_bars().with_columns(pl.col(c) - 200.0 for c in ("open", "high", "low", "close"))
    assert codes(df, adjustment="back_adjusted") == set()


def test_F_0_1_1_nan_in_required() -> None:
    df = make_bars().with_columns(
        pl.when(pl.int_range(pl.len()) == 2)
        .then(float("nan"))
        .otherwise(pl.col("volume"))
        .alias("volume")
    )
    assert codes(df) == {"nan_in_required"}


def test_F_0_1_1_null_in_required() -> None:
    df = make_bars().with_columns(
        pl.when(pl.int_range(pl.len()) == 2).then(None).otherwise(pl.col("open")).alias("open")
    )
    assert "nan_in_required" in codes(df)


def test_F_0_1_1_all_listed_issues_are_critical() -> None:
    df = make_bars().with_columns(pl.col("ts").dt.replace_time_zone(None)).drop("volume")
    issues = validate_bars(df, make_meta())
    assert issues and critical_issues(issues) == issues


# -- metadata --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("price_type", "last"),
        ("adjustment", "dividends"),
        ("session", "overnight"),
        ("feed", "otc"),
        ("volume_quality", "good"),
        ("bar_label", "middle"),
    ],
)
def test_F_0_1_1_metadata_rejects_invalid_enum(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        make_meta(**{field: value})


@pytest.mark.parametrize("tf", ["1h", "1d", "2H", "60min", "D", ""])
def test_F_0_1_1_metadata_rejects_invalid_timeframe(tf: str) -> None:
    with pytest.raises(ValidationError):
        make_meta(timeframe=tf)


@pytest.mark.parametrize("tf", ["1m", "5m", "15m", "1H", "4H", "1D"])
def test_F_0_1_1_metadata_accepts_valid_timeframes(tf: str) -> None:
    assert make_meta(timeframe=tf).timeframe == tf


def test_F_0_1_1_metadata_requires_fields_and_is_frozen() -> None:
    meta = make_meta()
    with pytest.raises(ValidationError):
        SeriesMetadata.model_validate({k: v for k, v in meta.model_dump().items() if k != "source"})
    with pytest.raises(ValidationError):
        meta.symbol = "OTHER"  # type: ignore[misc]


def test_F_0_1_1_metadata_rejects_naive_datetimes_and_bad_hash() -> None:
    with pytest.raises(ValidationError):
        make_meta(downloaded_at=dt.datetime(2024, 1, 1))
    with pytest.raises(ValidationError):
        make_meta(raw_refs=[{"path": "x", "sha256": "abc"}])
    with pytest.raises(ValidationError):
        make_meta(extra_field=1)


def test_F_0_1_1_metadata_json_round_trip() -> None:
    meta = make_meta()
    assert SeriesMetadata.model_validate_json(meta.model_dump_json()) == meta


def test_F_0_1_1_adapter_protocol_is_structural() -> None:
    class Dummy:
        def to_canonical(
            self, raw_paths: list, **params: object
        ) -> tuple[pl.DataFrame, SeriesMetadata]:
            return make_bars(), make_meta()

    assert isinstance(Dummy(), Adapter)


@pytest.mark.parametrize(
    "value",
    [
        "us_equity",
        "fx",
        "metal",
        "energy_cfd",
        "index_cfd",
        "futures",
        "crypto",
        "iran_equity",
        "aux",
    ],
)
def test_F_0_1_1_asset_class_accepts_enumeration(value: str) -> None:
    assert make_meta(asset_class=value).asset_class == value


@pytest.mark.parametrize("value", ["aux_index", "equity", "FX", "", "index"])
def test_F_0_1_1_asset_class_rejects_other_values(value: str) -> None:
    with pytest.raises(ValidationError):
        make_meta(asset_class=value)


def test_F_0_1_1_value_final_fields() -> None:
    meta = make_meta(
        value_final_time_local="16:15",
        value_final_tz="America/New_York",
        value_final_status="verified",
    )
    assert (meta.value_final_time_local, meta.value_final_tz, meta.value_final_status) == (
        "16:15",
        "America/New_York",
        "verified",
    )
    assert make_meta().value_final_status is None and make_meta().hash_version == 2
    for bad in ({"value_final_time_local": "4pm"}, {"value_final_time_local": "16:15:00"},
                {"value_final_tz": "Mars/Base"}, {"value_final_status": "maybe"}):  # fmt: skip
        with pytest.raises(ValidationError):
            make_meta(**bad)
