"""F-0.1.8 (T04k, D-702): retiring never-referenced derived snapshots -- the only exception to D-392.

A raw snapshot is never retired; neither is a reference, nor anything that was ever one. Files are
moved to a quarantine, never deleted, and every retirement is an event.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import polars as pl
import pytest
from fixtures.bars import make_bars, make_meta

from strategy_factory.core.errors import DataError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.store import SnapshotStore


def _setup(tmp_path: Path) -> tuple[SnapshotStore, Catalog, str, str]:
    store, cat = SnapshotStore(tmp_path / "s"), Catalog(tmp_path / "s")
    raw = cat.register(store.write_snapshot(make_bars(20), make_meta(symbol="EQ")))
    cat.set_reference("EQ", "1D", raw.snapshot_hash or "", note="raw")
    derived_meta = raw.model_copy(update={"snapshot_hash": None, "derived_from": raw.key()})
    derived = cat.register(store.write_snapshot(make_bars(21), derived_meta))
    return store, cat, raw.snapshot_hash or "", derived.snapshot_hash or ""


def test_F_0_1_8_D_702_a_never_referenced_derived_snapshot_is_retired(tmp_path: Path) -> None:
    store, cat, _raw, derived = _setup(tmp_path)
    pq, _meta = store.paths("test", "EQ", "1D", derived)
    digest = hashlib.sha256(pq.read_bytes()).hexdigest()
    rows = cat.retire([derived], note="D-702 re-derivation")
    assert rows.height == 1
    assert cat.table().filter(pl.col("snapshot_hash") == derived).height == 0
    ev = cat.events().filter(pl.col("event") == "retire")
    assert ev["snapshot_hash"].to_list() == [derived]
    moved = store.quarantine("test", "EQ", "1D", derived, tmp_path / "q")
    assert len(moved) == 2 and not pq.exists()
    assert hashlib.sha256(moved[0].read_bytes()).hexdigest() == digest  # bytes kept, not deleted


def test_F_0_1_8_D_702_a_raw_snapshot_is_never_retired(tmp_path: Path) -> None:
    _store, cat, raw, _derived = _setup(tmp_path)
    with pytest.raises(DataError, match="raw snapshots"):
        cat.retire([raw], note="no")
    assert cat.table().height == 2  # nothing changed


def test_F_0_1_8_D_702_a_snapshot_that_was_ever_a_reference_is_never_retired(
    tmp_path: Path,
) -> None:
    _store, cat, raw, derived = _setup(tmp_path)
    cat.set_reference("EQ", "1D", derived, note="briefly")
    cat.set_reference("EQ", "1D", raw, note="back to raw")
    with pytest.raises(DataError, match="were once a reference"):
        cat.retire([derived], note="no")
    assert cat.events().filter(pl.col("event") == "retire").height == 0
