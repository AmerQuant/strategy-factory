"""T04m: the aux as-of join end to end on the real store (F-0.1.11).

Local only; reads the store (``SFAC_DATA_ROOT``) through ``DataAccess`` with an **in-memory** split
ledger, so nothing is written to the registry or the store::

    uv run python scripts/analysis/T04m_join_check.py

For a US equity (daily and hourly) and the Dukascopy EURUSD 1H pilot: how many development bars
read a value of each aux series, how many are stale (-1), and the value read on a few known days,
next to the aux series' own date (addendum §5.3: an equity at the close of d reads VIX d-1, an FX
bar after 16:15 New York reads VIX d).

The Dukascopy pilots cover only Q1 2024 -- too short for a split (D-008), so ``DataAccess``
refuses them until T04j. For them the join itself (``build_view``) runs on the pilot's bars
directly: a check of the rule on real FX bars, not a data-access path.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np

from strategy_factory.core.errors import HoldoutAccessError, SfacError
from strategy_factory.data.auxiliary import build_view
from strategy_factory.data.config import load_aux_config, load_split_config
from strategy_factory.data.split import DataAccess, SplitManager

AUX = ("VIX", "SPX", "NDX", "RUT", "DJI", "TNX", "DXY")
CASES = (("AAPL", "1D"), ("AAPL", "1H"), ("EURUSD", "1H"))
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)


class MemoryLedger:
    """Split ledger in memory: the check leaves no trace in the registry."""

    def __init__(self) -> None:
        self.splits: dict[Any, dict[str, Any]] = {}

    def register_snapshot(self, meta: Any, is_reference: bool) -> None:
        pass

    def get_split(self, key: Any) -> dict[str, Any] | None:
        return self.splits.get(key)

    def add_split(self, split: Any) -> None:
        self.splits[split.key] = {**split.boundaries(), "expected_holdout_trades": None}

    def record_holdout_access(self, candidate_id: str, result: dict[str, Any]) -> None:
        raise HoldoutAccessError("the join check never opens a holdout")


def _date(us: int) -> str:
    return (EPOCH + dt.timedelta(microseconds=int(us))).strftime("%Y-%m-%d %H:%M")


def pilot_fx(mgr: SplitManager) -> None:
    """The join on the EURUSD 1H pilot's real bars (no split: see the module docstring)."""
    rules = load_aux_config().aux
    fx = mgr.catalog.get_reference("EURUSD", "1H")
    k = fx.key()
    bars = mgr.store.read_snapshot(k.source, k.symbol, k.timeframe, k.snapshot_hash, columns=["ts"])
    ts = bars["ts"].dt.epoch("us").to_numpy()
    probes = [
        dt.datetime(2024, 1, 10, 23, tzinfo=dt.UTC),  # ends 19:00 EST: DXY (19:15) of d not yet
        dt.datetime(2024, 3, 13, 19, tzinfo=dt.UTC),  # ends 16:00 EDT: VIX (16:15) of d not yet
        dt.datetime(2024, 3, 13, 20, tzinfo=dt.UTC),  # ends 17:00 EDT: VIX of d
    ]
    print(f"\nEURUSD 1H pilot ({len(ts)} bars, {_date(ts[0])[:10]} .. {_date(ts[-1])[:10]})")
    for aux in ("VIX", "DXY"):
        meta = mgr.catalog.get_reference(aux, "1D")
        a = meta.key()
        df = mgr.store.read_snapshot(a.source, a.symbol, a.timeframe, a.snapshot_hash).sort("ts")
        arrays = {c: df[c].to_numpy() for c in ("open", "high", "low", "close")}
        arrays["ts"] = df["ts"].dt.epoch("us").to_numpy()
        v = build_view(
            meta, arrays, fx, ts,
            extra_lag_days=rules.unverified_extra_lag_days,
            max_stale_sessions=rules.max_stale_sessions,
            sessions_file=rules.sessions_file,
        )  # fmt: skip
        print(f"  {aux:<4} bars {v.idx.size:>6}  none/stale {int((v.idx < 0).sum()):>5}")
        for t in probes:
            i = int(np.searchsorted(ts, (t - EPOCH) // dt.timedelta(microseconds=1)))
            got = _date(v.ts[v.idx[i]])[:10] if v.idx[i] >= 0 else "none"
            print(
                f"    bar {_date(ts[i])} UTC (decision {_date(v.decision_us[i])}) reads {aux} of {got}"
            )


def main() -> None:
    mgr = SplitManager(MemoryLedger(), load_split_config())
    access = DataAccess(mgr)
    for symbol, tf in CASES:
        try:
            split = access.split(symbol, tf)
        except SfacError as exc:
            print(f"{symbol} {tf}: not readable ({exc})")
            continue
        print(
            f"\n{symbol} {tf}: development {split.dev_start:%Y-%m-%d} .. {split.dev_end:%Y-%m-%d}"
        )
        for aux in AUX:
            v = access.aux(aux, symbol, tf)
            n = v.idx.size
            used = v.idx >= 0
            last = int(np.flatnonzero(used)[-1]) if used.any() else None
            sample = ""
            if last is not None:
                sample = (
                    f"; last bar {_date(v.decision_us[last])} UTC decision reads "
                    f"{aux} of {_date(v.ts[v.idx[last]])[:10]}"
                )
            print(
                f"  {aux:<4} bars {n:>6}  with a value {int(used.sum()):>6}  "
                f"none/stale {int((~used).sum()):>5}{sample}"
            )
    pilot_fx(mgr)


if __name__ == "__main__":
    main()
