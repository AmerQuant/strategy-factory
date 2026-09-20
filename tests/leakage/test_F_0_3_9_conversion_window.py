"""D-316 / F-0.3.9: conversion-pair bars never leave the traded symbol's window.

Mandatory gate. The conversion pair (GBPUSD) ends earlier than the traded symbol (EURGBP), so
the traded development window overlaps the pair's own holdout: the pair's bars are still read
only over the traded window, and the pair's holdout is never recorded or consumed.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from fixtures.bars import make_meta
from fixtures.registry_db import RUN_CONFIG
from fixtures.t05 import MemoryLedger, bars_from_close, random_close
from sqlalchemy import Engine

from strategy_factory.core.errors import DataError, HoldoutAccessError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import SplitConfig
from strategy_factory.data.conversion import conversion_for, load_fx_config
from strategy_factory.data.split import DataAccess, RegistryLedger, SplitManager
from strategy_factory.data.store import SnapshotStore

pytestmark = pytest.mark.leakage

T0 = dt.datetime(2012, 1, 2, tzinfo=dt.UTC)
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
REPO = Path(__file__).resolve().parents[2]


def us(t: dt.datetime) -> int:
    return (t - EPOCH) // dt.timedelta(microseconds=1)


def store_pair(root: Path, ledger: object) -> tuple[SplitManager, Catalog]:
    store, cat = SnapshotStore(root), Catalog(root)
    for sym, n, seed in (("EURGBP", 3000, 1), ("GBPUSD", 2600, 2)):
        ts = [T0 + dt.timedelta(days=i) for i in range(n)]
        df = bars_from_close(ts, random_close(n, seed=seed, start=1.3))
        meta = make_meta(symbol=sym, source_symbol=sym, asset_class="fx", source="dukascopy")
        m = cat.register(store.write_snapshot(df, meta.model_copy(update={"snapshot_hash": None})))
        cat.set_reference(sym, "1D", m.snapshot_hash or "")
    return SplitManager(ledger, SplitConfig(), store, cat), cat  # type: ignore[arg-type]


def test_F_0_3_9_conversion_bars_stay_in_the_traded_development_window(tmp_path: Path) -> None:
    ledger = MemoryLedger()
    mgr, _ = store_pair(tmp_path, ledger)
    da = DataAccess(mgr)
    traded = da.split("EURGBP", "1D")
    pair_split = da.split("GBPUSD", "1D")
    assert pair_split.holdout_start < traded.dev_end  # the windows really overlap
    conv = da.conversion_bars("GBPUSD", "EURGBP", "1D")
    assert int(conv["ts"][0]) >= us(traded.dev_start)
    assert int(conv["ts"][-1]) == us(traded.dev_end)  # up to the traded end, never beyond
    assert ledger.accesses == {}  # the pair's holdout is not recorded, let alone consumed
    for bad in ("EURGBP", "AAPL"):  # never the traded symbol, never a non-conversion symbol
        with pytest.raises(DataError, match="not a conversion pair"):
            da.conversion_bars(bad, "EURGBP", "1D")
    dev = da.arrays("EURGBP", "1D")
    fx = conversion_for(
        "GBP", dev["ts"], load_fx_config(REPO / "configs/data/fx_conversion.yaml"), conv
    )
    assert fx.source == "GBPUSD" and fx.fx_close.shape == dev["ts"].shape
    # a traded window extended beyond the conversion window is refused
    longer = np.append(dev["ts"], dev["ts"][-1] + 86_400_000_000)
    with pytest.raises(DataError, match="beyond the conversion window"):
        conversion_for(
            "GBP", longer, load_fx_config(REPO / "configs/data/fx_conversion.yaml"), conv
        )


def test_F_0_3_9_conversion_alignment_uses_only_known_values() -> None:
    from strategy_factory.data.conversion import align_pair

    day = 86_400_000_000
    traded = np.array([0, 1, 2, 3], dtype=np.int64) * day
    pair_ts = np.array([0, 1, 3], dtype=np.int64) * day  # bar 2 missing
    fo, fc = align_pair(
        traded, pair_ts, np.array([1.0, 1.1, 1.3]), np.array([1.05, 1.15, 1.35]), False
    )
    assert fo.tolist() == [1.0, 1.1, 1.15, 1.3]  # missing bar: last close before it
    assert fc.tolist() == [1.05, 1.15, 1.15, 1.35]
    inv_o, _ = align_pair(
        traded, pair_ts, np.array([2.0, 2.0, 2.0]), np.array([2.0, 2.0, 2.0]), True
    )
    assert inv_o.tolist() == [0.5] * 4
    with pytest.raises(DataError, match="before the first"):
        align_pair(traded - day, pair_ts, np.ones(3), np.ones(3), False)


@pytest.mark.db
def test_F_0_3_9_holdout_conversion_does_not_consume_the_pair_holdout(
    tmp_path: Path, registry_engine: Engine
) -> None:
    from strategy_factory.registry.writer import CandidateRecord, RegistryWriter

    mgr, _ = store_pair(tmp_path, RegistryLedger(registry_engine))
    w = RegistryWriter(registry_engine)
    run_id = w.start_run(RUN_CONFIG, seed=1, code_version="c" * 40)
    for cid, sym in (("cand-eurgbp", "EURGBP"), ("cand-gbpusd", "GBPUSD")):
        w.upsert_candidate(
            CandidateRecord(
                id=cid,
                run_id=run_id,
                symbol=sym,
                timeframe="1D",
                direction="long",
                edge_type="MR",
                spec={},
                spec_hash="h",
                current_stage="s06",
            )
        )
    for bad in (("EURGBP",), ("AAPL",)):  # the traded symbol itself, a non-conversion symbol
        with pytest.raises(DataError, match="not a conversion pair"):
            mgr.open_holdout_with_conversion("cand-eurgbp", "EURGBP", "1D", bad)
    bars, conv = mgr.open_holdout_with_conversion("cand-eurgbp", "EURGBP", "1D", ("GBPUSD",))
    split = mgr.registered(mgr.reference("EURGBP", "1D"))
    pair = conv["GBPUSD"]
    assert pair["ts"].size > 0
    assert int(pair["ts"][0]) >= us(split.holdout_start)
    assert int(pair["ts"][-1]) <= us(split.holdout_end)
    assert bars["ts"].min() == split.holdout_start
    hold_ts = bars["ts"].dt.epoch("us").to_numpy()
    cfg = load_fx_config(REPO / "configs/data/fx_conversion.yaml")
    assert conversion_for("GBP", hold_ts, cfg, pair).fx_close.shape == hold_ts.shape
    with pytest.raises(DataError, match="beyond the conversion window"):
        conversion_for("GBP", np.append(hold_ts, hold_ts[-1] + 86_400_000_000), cfg, pair)
    with pytest.raises(HoldoutAccessError):  # the traded candidate's access is one-shot
        mgr.open_holdout_with_conversion("cand-eurgbp", "EURGBP", "1D", ("GBPUSD",))
    # the pair's own holdout was not consumed: its candidate can open it once, not twice
    own = mgr.open_holdout("cand-gbpusd", "GBPUSD", "1D")
    assert isinstance(own, pl.DataFrame) and own.height > 0
    with pytest.raises(HoldoutAccessError):
        mgr.open_holdout("cand-gbpusd", "GBPUSD", "1D")


def test_F_0_3_9_hkd_uses_the_configured_peg() -> None:
    cfg = load_fx_config(REPO / "configs/data/fx_conversion.yaml")
    fx = conversion_for("HKD", np.arange(5, dtype=np.int64), cfg)
    assert fx.peg and fx.source == "peg:7.8"
    assert np.all(fx.fx_open == 1 / 7.80) and np.all(fx.fx_close == 1 / 7.80)
    assert not conversion_for("USD", np.arange(3, dtype=np.int64), cfg).peg
    with pytest.raises(DataError, match="bars are required"):
        conversion_for("EUR", np.arange(3, dtype=np.int64), cfg)
