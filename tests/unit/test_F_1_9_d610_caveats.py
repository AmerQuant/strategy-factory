"""D-610: the caveats a profile carries, read from a real (temporary) catalog.

The quality status and the failing checks from the snapshot's own quality report; the splice
markers and whether the series is a research window (D-713); whether it is derived, and whether
T04l trimmed it at a proven re-use boundary -- T04l tags both of its outputs "T04l re-use", so a
trim is the tag *without* a research-window marker.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import polars as pl
from fixtures.bars import make_meta

from strategy_factory.data.catalog import Catalog, Splice
from strategy_factory.data.quality import QUALITY_DIR
from strategy_factory.data.store import SnapshotStore
from strategy_factory.stages.reference import T04L_TRIM_TAG, ReferenceInfo

WINDOW = Splice(
    boundary=dt.date(2021, 3, 1),
    role="research_window",
    reason="cusip_after_only",
    evidence="CUSIP after 12345X100",
)


def stored(root: Path, symbol: str, **meta: Any) -> Any:
    store, catalog = SnapshotStore(root), Catalog(root)
    ts = [dt.datetime(2020, 1, 2, tzinfo=dt.UTC) + dt.timedelta(days=i) for i in range(20)]
    bars = pl.DataFrame(
        {
            "ts": ts,
            "open": [10.0] * 20,
            "high": [10.5] * 20,
            "low": [9.5] * 20,
            "close": [10.0] * 20,
            "volume": [1.0] * 20,
        }
    )
    m = catalog.register(
        store.write_snapshot(
            bars, make_meta(source="alpaca", source_symbol=symbol, symbol=symbol, **meta)
        )
    )
    catalog.set_reference(symbol, "1D", m.snapshot_hash)
    return catalog, m


def report(root: Path, snapshot_hash: str, checks: dict[str, str]) -> None:
    out = root / QUALITY_DIR
    out.mkdir(parents=True, exist_ok=True)
    body = {"status": "warning", "checks": [{"code": c, "status": s} for c, s in checks.items()]}
    (out / f"{snapshot_hash}.json").write_text(json.dumps(body), encoding="utf-8")


def test_F_1_9_d610_quality_status_and_the_failing_checks(tmp_path: Path) -> None:
    catalog, m = stored(tmp_path, "AAA")
    catalog.set_quality_status(m.key(), "warning")
    report(tmp_path, m.snapshot_hash, {"schema": "pass", "price_spikes": "warning", "dst": "skip",
                                       "missing_bars": "warning"})  # fmt: skip
    cav = ReferenceInfo(catalog).caveats("AAA", "1D")
    assert cav.quality_status == "warning"
    assert cav.warning_checks == ("missing_bars", "price_spikes")  # passing and skipped left out
    assert not cav.research_window and not cav.trimmed and not cav.derived


def test_F_1_9_d610_a_research_window_is_not_a_trim(tmp_path: Path) -> None:
    catalog, m = stored(tmp_path, "BBB", notes=f"{T04L_TRIM_TAG} (D-713): research window")
    catalog.mark_splices(m.key(), (WINDOW,), note="T04l")
    cav = ReferenceInfo(catalog).caveats("BBB", "1D")
    assert cav.research_window and not cav.trimmed
    assert cav.splices == (
        {"role": "research_window", "boundary": "2021-03-01", "reason": "cusip_after_only"},
    )


def test_F_1_9_d610_a_t04l_trim_is_the_tag_without_a_window(tmp_path: Path) -> None:
    base_catalog, base = stored(tmp_path, "CCC")
    catalog, _ = stored(
        tmp_path / "derived",
        "DDD",
        notes=f"{T04L_TRIM_TAG} (D-709): history cut at a proven re-use boundary",
        derived_from=base.key(),
    )
    cav = ReferenceInfo(catalog).caveats("DDD", "1D")
    assert cav.trimmed and cav.derived and not cav.research_window
    assert ReferenceInfo(base_catalog).caveats("CCC", "1D").trimmed is False


def test_F_1_9_d610_no_quality_report_means_no_checks_listed(tmp_path: Path) -> None:
    catalog, _ = stored(tmp_path, "EEE")
    assert ReferenceInfo(catalog).caveats("EEE", "1D").warning_checks == ()
