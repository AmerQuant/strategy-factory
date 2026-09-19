"""F-0.1.8: content hash, immutable snapshot store and catalog."""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

import polars as pl
import pytest
from fixtures.bars import T0, make_bars, make_meta
from polars.testing import assert_frame_equal

from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.data import store as store_mod
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.hashing import content_hash, file_sha256, normalize
from strategy_factory.data.store import SnapshotStore, read_snapshot, safe_component, write_snapshot


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "store"
    monkeypatch.setenv("SFAC_DATA_ROOT", str(root))
    monkeypatch.chdir(tmp_path)
    return root


# -- hashing -----------------------------------------------------------------------------
def test_F_0_1_8_hash_independent_of_row_order() -> None:
    df = make_bars(20)
    shuffled = df.sample(fraction=1.0, shuffle=True, seed=7)
    assert not shuffled.equals(df)
    assert content_hash(shuffled) == content_hash(df)


def test_F_0_1_8_hash_independent_of_column_order_and_chunks() -> None:
    df = make_bars(10)
    chunked = pl.concat([df.slice(5), df.slice(0, 5)], rechunk=False).select(reversed(df.columns))
    assert content_hash(chunked) == content_hash(df)


@pytest.mark.parametrize("compression", ["zstd", "snappy", "gzip", "lz4", "uncompressed"])
def test_F_0_1_8_hash_independent_of_parquet_compression(compression: str) -> None:
    df = make_bars(50)
    buf = io.BytesIO()
    df.write_parquet(buf, compression=compression, row_group_size=7)
    buf.seek(0)
    assert content_hash(pl.read_parquet(buf)) == content_hash(df)


def test_F_0_1_8_changing_one_value_changes_hash() -> None:
    df = make_bars(10)
    changed = df.with_columns(
        pl.when(pl.int_range(pl.len()) == 3)
        .then(pl.col("close") + 1e-9)
        .otherwise(pl.col("close"))
        .alias("close")
    )
    assert content_hash(changed) != content_hash(df)


def test_F_0_1_8_file_sha256(tmp_path: Path) -> None:
    p = tmp_path / "a.bin"
    p.write_bytes(b"abc")
    assert file_sha256(p) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


# -- store -------------------------------------------------------------------------------
def test_F_0_1_8_round_trip_identical(data_root: Path) -> None:
    df = make_bars(8)
    meta = write_snapshot(df, make_meta())
    assert meta.snapshot_hash == content_hash(df)
    assert (meta.row_count, meta.first_ts, meta.last_ts) == (8, df["ts"].min(), df["ts"].max())
    back = read_snapshot("test", "TEST", "1D", meta.snapshot_hash)
    assert_frame_equal(back, normalize(df))


def test_F_0_1_8_layout_and_sidecar(data_root: Path) -> None:
    meta = write_snapshot(make_bars(), make_meta())
    d = data_root / "test" / "TEST" / "1D"
    assert (d / f"{meta.snapshot_hash}.parquet").is_file()
    stored = SnapshotStore().read_metadata("test", "TEST", "1D", meta.snapshot_hash or "")
    assert stored == meta


def test_F_0_1_8_write_is_idempotent(data_root: Path) -> None:
    first = write_snapshot(make_bars(), make_meta())
    pq = data_root / "test" / "TEST" / "1D" / f"{first.snapshot_hash}.parquet"
    mtime = pq.stat().st_mtime_ns
    second = write_snapshot(make_bars().reverse(), make_meta(notes="different metadata"))
    assert second == first  # stored metadata returned, nothing rewritten
    assert pq.stat().st_mtime_ns == mtime
    assert len(list(pq.parent.iterdir())) == 2


def test_F_0_1_8_snapshot_is_read_only_and_cannot_be_modified(data_root: Path) -> None:
    meta = write_snapshot(make_bars(), make_meta())
    pq, meta_path = SnapshotStore().paths("test", "TEST", "1D", meta.snapshot_hash or "")
    for path in (pq, meta_path):
        with pytest.raises(PermissionError):
            path.write_bytes(b"overwrite")
        with pytest.raises(PermissionError), path.open("ab") as fh:
            fh.write(b"append")
    assert read_snapshot("test", "TEST", "1D", meta.snapshot_hash or "").height == 5


def test_F_0_1_8_changed_content_is_a_new_snapshot(data_root: Path) -> None:
    a = write_snapshot(make_bars(5), make_meta())
    b = write_snapshot(make_bars(6), make_meta())
    assert a.snapshot_hash != b.snapshot_hash
    assert read_snapshot("test", "TEST", "1D", a.snapshot_hash or "").height == 5


def test_F_0_1_8_critical_issue_blocks_write(data_root: Path) -> None:
    bad = make_bars().with_columns((pl.col("high") + 5).alias("close"))
    with pytest.raises(DataError, match="ohlc_outside_range") as exc:
        write_snapshot(bad, make_meta())
    assert exc.value.symbol == "TEST"
    assert not data_root.exists() or not any(data_root.rglob("*.parquet"))


def test_F_0_1_8_unsorted_input_is_stored_sorted(data_root: Path) -> None:
    df = make_bars(6)
    meta = write_snapshot(df.reverse(), make_meta())
    assert read_snapshot("test", "TEST", "1D", meta.snapshot_hash or "")["ts"].is_sorted()


def test_F_0_1_8_read_with_columns_and_range(data_root: Path) -> None:
    meta = write_snapshot(make_bars(10), make_meta())
    part = read_snapshot(
        "test",
        "TEST",
        "1D",
        meta.snapshot_hash or "",
        columns=["ts", "close"],
        start=T0 + dt.timedelta(days=2),
        end=T0 + dt.timedelta(days=5),
    )
    assert part.columns == ["ts", "close"]
    assert part["ts"].to_list() == [T0 + dt.timedelta(days=d) for d in (2, 3, 4)]


def test_F_0_1_8_missing_snapshot_raises(data_root: Path) -> None:
    with pytest.raises(DataError):
        read_snapshot("test", "TEST", "1D", "f" * 64)


def test_F_0_1_8_missing_data_root_is_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SFAC_DATA_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    with pytest.raises(ConfigError, match="SFAC_DATA_ROOT"):
        store_mod.data_root()
    with pytest.raises(ConfigError):
        Catalog()


@pytest.mark.parametrize(
    ("raw", "safe"),
    [
        ("AAPL", "AAPL"),
        ("BRK.B", "BRK.B"),
        ("BTC/USDT", "BTC_USDT"),
        ("^VIX", "^VIX"),
        ("@ES", "@ES"),
        ("AUX", "AUX_"),
        ("CON", "CON_"),
    ],
)
def test_F_0_1_8_safe_path_component(raw: str, safe: str) -> None:
    assert safe_component(raw) == safe


# -- catalog -----------------------------------------------------------------------------
def test_F_0_1_8_register_requires_stored_meta(data_root: Path) -> None:
    with pytest.raises(DataError):
        Catalog().register(make_meta())


def test_F_0_1_8_register_is_idempotent(data_root: Path) -> None:
    cat = Catalog()
    meta = write_snapshot(make_bars(), make_meta())
    cat.register(meta)
    cat.register(meta)
    assert cat.list_snapshots().height == 1
    assert cat.events()["event"].to_list() == ["register"]


def test_F_0_1_8_set_reference_keeps_exactly_one_and_logs(data_root: Path) -> None:
    cat = Catalog()
    a = cat.register(write_snapshot(make_bars(5), make_meta()))
    b = cat.register(write_snapshot(make_bars(6), make_meta()))
    other = cat.register(
        write_snapshot(make_bars(5), make_meta(symbol="OTHER", source_symbol="OTHER"))
    )
    cat.set_reference("OTHER", "1D", other.snapshot_hash or "", note="other")
    cat.set_reference("TEST", "1D", a.snapshot_hash or "", note="first")
    cat.set_reference("TEST", "1D", b.snapshot_hash or "", note="switch")
    cat.set_reference("TEST", "1D", b.snapshot_hash or "", note="no-op")

    refs = cat.list_snapshots(symbol="TEST", timeframe="1D").filter(pl.col("is_reference"))
    assert refs["snapshot_hash"].to_list() == [b.snapshot_hash]
    assert cat.get_reference("TEST", "1D") == b
    assert cat.get_reference("OTHER", "1D") == other  # untouched by TEST's changes

    ev = cat.events().filter(pl.col("event") == "set_reference")
    assert ev["note"].to_list() == ["other", "first", "switch"]  # the no-op is not logged
    assert ev["previous_reference"].to_list() == [None, None, a.snapshot_hash]


def test_F_0_1_8_set_reference_requires_registered_snapshot(data_root: Path) -> None:
    with pytest.raises(DataError):
        Catalog().set_reference("TEST", "1D", "a" * 64)


def test_F_0_1_8_get_reference_without_reference_raises(data_root: Path) -> None:
    cat = Catalog()
    cat.register(write_snapshot(make_bars(), make_meta()))
    with pytest.raises(DataError, match="no reference"):
        cat.get_reference("TEST", "1D")
    assert not cat.has_reference("TEST", "1D")


def test_F_0_1_8_catalog_round_trips_metadata(data_root: Path) -> None:
    cat = Catalog()
    meta = cat.register(write_snapshot(make_bars(), make_meta(notes="n1")))
    cat.set_reference("TEST", "1D", meta.snapshot_hash or "")
    assert cat.get_reference("TEST", "1D") == meta
    assert not any(p.name.endswith(".partial") for p in data_root.iterdir())


def test_F_0_1_8_v1_sidecar_and_old_catalog_are_read_as_hash_version_1(data_root: Path) -> None:
    """Snapshots written before hash_version existed stay readable (and are version 1)."""
    import json

    meta = write_snapshot(make_bars(), make_meta())
    assert meta.hash_version == 2
    store = SnapshotStore()
    _, sidecar = store.paths("test", "TEST", "1D", meta.snapshot_hash or "")
    old = json.loads(sidecar.read_text(encoding="utf-8"))
    for key in ("hash_version", "value_final_time_local", "value_final_tz", "value_final_status"):
        old.pop(key)
    sidecar.chmod(0o644)
    sidecar.write_text(json.dumps(old), encoding="utf-8")
    assert store.read_metadata("test", "TEST", "1D", meta.snapshot_hash or "").hash_version == 1

    cat = Catalog()
    cat.register(meta)
    legacy = cat.table().drop(
        ["hash_version", "value_final_time_local", "value_final_tz", "value_final_status"]
    )
    legacy.write_parquet(cat.path)  # a catalog file from before these columns existed
    table = cat.table()
    assert table["hash_version"].to_list() == [1]
    cat.set_reference("TEST", "1D", meta.snapshot_hash or "", note="rehash v1→v2")
    assert cat.get_reference("TEST", "1D").hash_version == 1
