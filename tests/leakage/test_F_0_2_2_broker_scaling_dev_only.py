"""F-0.2.2 / D-340: the Dukascopy -> broker spread scaling is fitted on development bars only.

Mandatory leakage gate: never skipped, weakened or deleted.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
from fixtures.t05 import MemoryLedger, bars_from_close, fx_hours, fx_meta, random_close

from strategy_factory.costs.arrays import resolve_from_data, week_open_mask
from strategy_factory.costs.profile import load_profiles
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import SplitConfig
from strategy_factory.data.split import DataAccess, SplitManager
from strategy_factory.data.store import SnapshotStore

REPO_COSTS = Path(__file__).resolve().parents[2] / "configs" / "costs"


def test_F_0_2_2_broker_scaling_never_sees_the_holdout(tmp_path: Path) -> None:
    ts = fx_hours(
        dt.datetime(2021, 1, 3, 22, tzinfo=dt.UTC), dt.datetime(2023, 12, 29, 21, tzinfo=dt.UTC)
    )
    n = len(ts)
    hours = np.array([t.hour for t in ts])
    shape = np.where(hours == 21, 1.4e-4, 2e-5)  # a rollover widening, like the pilot
    store, cat = SnapshotStore(tmp_path), Catalog(tmp_path)
    first = cat.register(
        store.write_snapshot(
            bars_from_close(ts, random_close(n), spread=shape), fx_meta(snapshot_hash=None)
        )
    )
    cat.set_reference("EURUSD", "1H", first.snapshot_hash or "")
    mgr = SplitManager(MemoryLedger(), SplitConfig(), store, cat)
    split = DataAccess(mgr).split("EURUSD", "1H")
    profile = load_profiles(REPO_COSTS)["moneta_EURUSD+"]
    broker = profile.spread.model_dump()["broker_spread"]

    clean_dev = DataAccess(mgr).arrays("EURUSD", "1H")
    clean, clean_table = resolve_from_data(profile, clean_dev)

    # same bars, holdout spreads x 1000: a new snapshot becomes the reference
    hold = np.array([t >= split.holdout_start for t in ts])
    poisoned = bars_from_close(ts, random_close(n), spread=np.where(hold, shape * 1000, shape))
    second = cat.register(store.write_snapshot(poisoned, fx_meta(snapshot_hash=None)))
    cat.set_reference("EURUSD", "1H", second.snapshot_hash or "")
    dev = DataAccess(mgr).arrays("EURUSD", "1H")
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
    holdout_us = (split.holdout_start - epoch) // dt.timedelta(microseconds=1)
    assert int(dev["ts"][-1]) < holdout_us

    resolved, table = resolve_from_data(profile, dev)
    assert np.array_equal(table.full_spread, clean_table.full_spread)  # factor and shape unchanged
    assert table.week_open == clean_table.week_open is not None  # the week-open key too (D-716)
    assert resolved.source_note == clean.source_note  # it records the fitted factor
    hourly = np.asarray(resolved.spread.model_dump()["hourly"])
    dev_ts = np.asarray(dev["ts"], dtype=np.int64)
    dev_hours = (dev_ts // 3_600_000_000) % 24
    # what each development bar is charged: its UTC hour, or the week-open key (D-716)
    charged = np.where(
        week_open_mask(dev_ts, "1H"), resolved.spread.model_dump()["week_open"], hourly[dev_hours]
    )
    assert abs(float(np.mean(charged)) / broker - 1.0) < 1e-12
