"""F-0.6.1 / D-306 -- CRITICAL: only stage 6 may open a holdout, enforced in code.

The allowed stage is the module constant ``data.split.HOLDOUT_STAGE``. It is deliberately
**not** a config value, so no YAML, pipeline config or environment can widen holdout access;
the tests below prove that, that a refused caller writes nothing to the ledger, and that the
one-shot rule (D-008) is unchanged.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import polars as pl
import pytest
import yaml
from fixtures.bars import make_meta
from fixtures.t05 import MemoryLedger, bars_from_close, random_close
from sqlalchemy import Engine

from strategy_factory.core.config import PipelineConfig
from strategy_factory.core.errors import HoldoutAccessError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import SplitConfig
from strategy_factory.data.split import HOLDOUT_STAGE, DataAccess, SplitManager
from strategy_factory.data.store import SnapshotStore

REPO = Path(__file__).resolve().parents[2]
T0 = dt.datetime(2000, 1, 3, tzinfo=dt.UTC)
OTHER_STAGES = ("s01_probe", "s01_edge", "s02_screen", "s03_entry", "s04_exit", "s05_filter",
                "s07_stats", "", "S06_ROBUST", "s06_robust ")  # fmt: skip


def daily(n: int) -> pl.DataFrame:
    return bars_from_close([T0 + dt.timedelta(days=i) for i in range(n)], random_close(n))


def manager(root: Path) -> tuple[SplitManager, MemoryLedger]:
    store, cat = SnapshotStore(root), Catalog(root)
    meta = cat.register(store.write_snapshot(daily(3000), make_meta()))
    cat.set_reference(meta.symbol, meta.timeframe, meta.snapshot_hash or "")
    ledger = MemoryLedger()
    return SplitManager(ledger, SplitConfig(), store, cat), ledger


def test_F_0_6_1_d306_allowed_stage_is_stage_six() -> None:
    assert HOLDOUT_STAGE == "s06_robust"


@pytest.mark.parametrize("stage", OTHER_STAGES)
def test_F_0_6_1_d306_any_other_stage_is_refused_and_writes_nothing(
    tmp_path: Path, stage: str
) -> None:
    mgr, ledger = manager(tmp_path)
    reads: list[str] = []
    orig = mgr.store.read_snapshot
    mgr.store.read_snapshot = lambda *a, **k: reads.append("read") or orig(*a, **k)  # type: ignore[method-assign]
    with pytest.raises(HoldoutAccessError, match="may not open a holdout"):
        mgr.open_holdout("cand-1", "TEST", "1D", stage=stage)
    assert ledger.accesses == {}  # the one-shot access was not spent
    assert reads == []  # and no bar was read
    # the same candidate can still open its holdout from stage 6 afterwards
    assert mgr.open_holdout("cand-1", "TEST", "1D", stage=HOLDOUT_STAGE).height > 0


def test_F_0_6_1_d306_stage_six_works_once(tmp_path: Path) -> None:
    mgr, ledger = manager(tmp_path)
    split = DataAccess(mgr).split("TEST", "1D")
    hold = mgr.open_holdout("cand-1", "TEST", "1D", stage=HOLDOUT_STAGE)
    assert hold["ts"].min() == split.holdout_start and hold["ts"].max() == split.holdout_end
    assert ledger.accesses["cand-1"]["snapshot_hash"] is not None
    with pytest.raises(HoldoutAccessError):
        mgr.open_holdout("cand-1", "TEST", "1D", stage=HOLDOUT_STAGE)


def test_F_0_6_1_d306_the_stage_argument_is_keyword_only(tmp_path: Path) -> None:
    mgr, _ = manager(tmp_path)
    with pytest.raises(TypeError, match="stage"):
        mgr.open_holdout("cand-1", "TEST", "1D")  # type: ignore[call-arg]


@pytest.mark.parametrize("stage", ["s05_filter", "s07_stats"])
def test_F_0_6_1_d306_conversion_path_refuses_the_same_callers(tmp_path: Path, stage: str) -> None:
    mgr, ledger = manager(tmp_path)
    with pytest.raises(HoldoutAccessError, match="may not open a holdout"):
        mgr.open_holdout_with_conversion("cand-1", "TEST", "1D", ("EURUSD",), stage=stage)
    assert ledger.accesses == {}


def test_F_0_6_1_d306_development_access_needs_no_stage(tmp_path: Path) -> None:
    """D-316: the conversion arrays of a development run never go through ``open_holdout``."""
    mgr, ledger = manager(tmp_path)
    access = DataAccess(mgr)
    assert access.bars("TEST", "1D").height > 0
    assert access.arrays("TEST", "1D")["close"].size > 0
    assert ledger.accesses == {}


# -- no config can change the allowed stage --------------------------------------------------
def test_F_0_6_1_d306_no_config_model_accepts_a_holdout_stage_field() -> None:
    for model, kwargs in (
        (PipelineConfig, {"symbols": ["SPY"], "timeframes": ["1D"], "stages": ["s01_edge"]}),
        (SplitConfig, {}),
    ):
        with pytest.raises(ValueError, match="holdout_stage"):
            model.model_validate({**kwargs, "holdout_stage": "s01_probe"})  # extra="forbid"


def test_F_0_6_1_d306_a_config_with_a_holdout_stage_key_changes_nothing(tmp_path: Path) -> None:
    """Even if such a file existed on disk, the guard still refuses stage 5."""
    path = tmp_path / "split_like.yaml"
    path.write_text(yaml.safe_dump({"holdout_stage": "s05_filter"}), encoding="utf-8")
    loaded: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["holdout_stage"] == "s05_filter"
    mgr, ledger = manager(tmp_path)
    with pytest.raises(HoldoutAccessError):
        mgr.open_holdout("c", "TEST", "1D", stage=loaded["holdout_stage"])
    assert ledger.accesses == {}


def test_F_0_6_1_d306_no_repo_config_defines_the_allowed_stage() -> None:
    """The allowed stage lives in code only: no YAML under ``configs/`` sets it (D-306)."""
    hits = [
        p.relative_to(REPO).as_posix()
        for p in (REPO / "configs").rglob("*.yaml")
        if "holdout_stage" in p.read_text(encoding="utf-8")
    ]
    assert hits == []


@pytest.mark.db
def test_F_0_6_1_d306_registry_ledger_records_nothing_for_a_refused_stage(
    registry_engine: Engine, tmp_path: Path
) -> None:
    from fixtures.registry_db import RUN_CONFIG
    from sqlalchemy import func, select

    from strategy_factory.data.split import RegistryLedger
    from strategy_factory.registry.tables import holdout_access
    from strategy_factory.registry.writer import CandidateRecord, RegistryWriter

    store, cat = SnapshotStore(tmp_path), Catalog(tmp_path)
    meta = cat.register(store.write_snapshot(daily(3000), make_meta()))
    cat.set_reference(meta.symbol, meta.timeframe, meta.snapshot_hash or "")
    mgr = SplitManager(RegistryLedger(registry_engine), SplitConfig(), store, cat)
    writer = RegistryWriter(registry_engine)
    writer.upsert_candidate(
        CandidateRecord(
            id="cand-1",
            run_id=writer.start_run(RUN_CONFIG, seed=1),
            symbol="TEST",
            timeframe="1D",
            direction="long",
            edge_type="MR",
            spec={},
            spec_hash="h",
            current_stage="s06_robust",
        )
    )

    def rows() -> int:
        with registry_engine.connect() as conn:
            return int(conn.execute(select(func.count()).select_from(holdout_access)).scalar_one())

    with pytest.raises(HoldoutAccessError, match="may not open a holdout"):
        mgr.open_holdout("cand-1", "TEST", "1D", stage="s05_filter")
    assert rows() == 0
    assert mgr.open_holdout("cand-1", "TEST", "1D", stage=HOLDOUT_STAGE).height > 0
    assert rows() == 1
    with pytest.raises(HoldoutAccessError):
        mgr.open_holdout("cand-1", "TEST", "1D", stage=HOLDOUT_STAGE)
    assert rows() == 1
