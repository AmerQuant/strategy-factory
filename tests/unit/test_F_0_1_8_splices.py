"""F-0.1.8 / F-0.1.6 (T04l, D-709): the splice marker lives on the snapshot key in the catalog.

A reader of the store learns that a series joins two companies from the store itself: the catalog
column, a ``splice`` event per change, and the snapshot's own quality report.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from fixtures.bars import make_meta

from strategy_factory.core.errors import DataError
from strategy_factory.data.catalog import Catalog, Splice
from strategy_factory.data.config import QualityConfig
from strategy_factory.data.quality import QUALITY_DIR, check_snapshot
from strategy_factory.data.store import SnapshotStore

FULL = Splice(
    boundary=dt.date(2025, 8, 1),
    role="full_history",
    reason="cusip_after_only",
    evidence="CUSIP after 12345X100 (cash_dividends)",
)
WINDOW = FULL.model_copy(update={"role": "research_window"})


def _stored(tmp_path: Path) -> tuple[SnapshotStore, Catalog, object]:
    import polars as pl

    store = SnapshotStore(tmp_path)
    catalog = Catalog(tmp_path)
    ts = [dt.datetime(2020, 1, 2, tzinfo=dt.UTC) + dt.timedelta(days=i) for i in range(30)]
    bars = pl.DataFrame(
        {
            "ts": ts,
            "open": [10.0] * 30,
            "high": [10.5] * 30,
            "low": [9.5] * 30,
            "close": [10.0] * 30,
            "volume": [1.0] * 30,
        }
    )
    meta = make_meta(source="alpaca", source_symbol="PCL", symbol="PCL", session="exchange")
    return store, catalog, catalog.register(store.write_snapshot(bars, meta))


def test_F_0_1_8_T04l_a_marker_is_recorded_read_back_and_logged(tmp_path: Path) -> None:
    _, catalog, meta = _stored(tmp_path)
    key = meta.key()  # type: ignore[attr-defined]
    assert catalog.splices(key) == ()
    assert catalog.mark_splices(key, (FULL,), note="T04l") is True
    assert catalog.splices(key) == (FULL,)
    assert catalog.events()["event"].to_list()[-1] == "splice"
    assert catalog.mark_splices(key, (FULL,), note="T04l") is False  # unchanged: no event
    assert catalog.events()["event"].to_list().count("splice") == 1


def test_F_0_1_8_T04l_an_older_catalog_without_the_column_reads_no_marker(tmp_path: Path) -> None:
    import polars as pl

    _, catalog, meta = _stored(tmp_path)
    pl.read_parquet(catalog.path).drop("splices").write_parquet(catalog.path)
    assert catalog.splices(meta.key()) == ()  # type: ignore[attr-defined]


def test_F_0_1_8_T04l_an_unregistered_snapshot_cannot_be_marked(tmp_path: Path) -> None:
    _, catalog, meta = _stored(tmp_path)
    other = meta.key().model_copy(update={"snapshot_hash": "0" * 64})  # type: ignore[attr-defined]
    with pytest.raises(DataError, match="not registered"):
        catalog.mark_splices(other, (FULL,), note="x")


def test_F_0_1_6_T04l_the_quality_report_states_the_splice(tmp_path: Path) -> None:
    store, catalog, meta = _stored(tmp_path)
    key = meta.key()  # type: ignore[attr-defined]
    catalog.mark_splices(key, (FULL,), note="T04l")
    rep = check_snapshot(meta, store, catalog, QualityConfig())  # type: ignore[arg-type]
    check = next(c for c in rep.checks if c.code == "known_splice")
    assert check.status == "fail" and check.severity == "warning"
    assert "2025-08-01" in check.message and "cusip_after_only" in check.message
    assert rep.status in ("warning", "critical")
    js = json.loads((tmp_path / QUALITY_DIR / f"{key.snapshot_hash}.json").read_text("utf-8"))
    assert any(c["code"] == "known_splice" and c["status"] == "fail" for c in js["checks"])


def test_F_0_1_6_T04l_a_research_window_passes_and_names_its_boundary(tmp_path: Path) -> None:
    store, catalog, meta = _stored(tmp_path)
    catalog.mark_splices(meta.key(), (WINDOW,), note="T04l")  # type: ignore[attr-defined]
    rep = check_snapshot(meta, store, catalog, QualityConfig())  # type: ignore[arg-type]
    check = next(c for c in rep.checks if c.code == "known_splice")
    assert check.status == "pass" and "research window from 2025-08-01" in check.message


def test_F_0_1_8_T04l_data_access_shows_the_reference_marker_and_reads_no_bar(
    tmp_path: Path,
) -> None:
    """Stage 1 sees the marker through DataAccess; the read touches no bar and no split."""
    from fixtures.t05 import MemoryLedger

    from strategy_factory.data.config import SplitConfig
    from strategy_factory.data.split import DataAccess, SplitManager

    store, catalog, meta = _stored(tmp_path)
    key = meta.key()  # type: ignore[attr-defined]
    catalog.set_reference("PCL", "1D", key.snapshot_hash)
    catalog.mark_splices(key, (WINDOW,), note="T04l")
    ledger = MemoryLedger()
    mgr = SplitManager(ledger, SplitConfig(), store, catalog)
    reads: list[str] = []
    orig = store.read_snapshot
    store.read_snapshot = lambda *a, **k: reads.append("read") or orig(*a, **k)  # type: ignore[method-assign]
    assert DataAccess(mgr).splices("PCL", "1D") == (WINDOW,)
    assert reads == [] and ledger.accesses == {}
