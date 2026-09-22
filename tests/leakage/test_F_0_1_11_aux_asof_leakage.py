"""F-0.1.11 leakage gate (T04m): no traded bar ever reads an aux value that is not yet final.

Acceptance of F-0.1.11: no bar has access to a simultaneous or future value of an aux series.
Two properties, on random aux calendars, close times, lags and traded bars (US equity daily and
hourly, FX daily and hourly):

* every value read is final **strictly before** the reading bar's decision instant;
* **data truncation:** cutting the aux series after any instant T -- and cutting the traded bars
  after any bar -- changes nothing for a bar whose decision instant is at or before T.

Mandatory leakage gate: never skipped, weakened or deleted (CLAUDE.md rule 9).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
from fixtures.bars import make_meta
from fixtures.hypothesis_budget import examples
from fixtures.t05 import FAKE_HASH
from hypothesis import given, settings
from hypothesis import strategies as st

from strategy_factory.data.auxiliary import AuxView, build_view, nyse_calendar
from strategy_factory.data.schema import SeriesMetadata

REPO = Path(__file__).resolve().parents[2]
SESSIONS = REPO / "configs" / "calendars" / "nyse_sessions.csv"
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
US_DAY = 86_400_000_000
US_HOUR = 3_600_000_000
_CAL = nyse_calendar(SESSIONS)
NYSE_DAYS = [int(d) for d in _CAL.days if 19_000 <= d <= 19_900]  # 2022-01 .. 2024-06
WEEKDAYS = [d for d in range(19_000, 19_901) if (d + 3) % 7 < 5]

CLOSES = [("16:15", "America/New_York", "verified"), ("17:15", "America/New_York", "verified"),
          ("19:15", "America/New_York", "verified"), (None, None, "to_verify")]  # fmt: skip
TRADED = {
    "equity_1D": ("us_equity", "1D"),
    "equity_1H": ("us_equity", "1H"),
    "fx_1D": ("fx", "1D"),
    "fx_1H": ("fx", "1H"),
}


def aux_meta(close: tuple[str | None, str | None, str], zone: str) -> SeriesMetadata:
    return make_meta(
        source="yahoo", symbol="AUX", source_symbol="^AUX", asset_class="aux", adjustment="raw",
        session="exchange", feed="none", volume_quality="none", original_tz=zone,
        value_final_time_local=close[0], value_final_tz=close[1], value_final_status=close[2],
        snapshot_hash=FAKE_HASH,
    )  # fmt: skip


def traded_meta(kind: str) -> SeriesMetadata:
    cls, tf = TRADED[kind]
    return make_meta(symbol="T", asset_class=cls, timeframe=tf, snapshot_hash=FAKE_HASH)


def traded_ts(kind: str, days: list[int]) -> np.ndarray:
    cls, tf = TRADED[kind]
    if tf == "1D":
        return np.array([d * US_DAY for d in days], dtype=np.int64)
    # hourly: every hour of the day (13:00-20:00 UTC for equities, all 24 for FX)
    hours = range(13, 20) if cls == "us_equity" else range(24)
    return np.array([d * US_DAY + h * US_HOUR for d in days for h in hours], dtype=np.int64)


def aux_arrays(days: list[int]) -> dict[str, Any]:
    c = np.array(days, dtype=np.float64)  # the value is its own date: easy to compare
    return {
        "ts": np.array(days, dtype=np.int64) * US_DAY,
        "open": c,
        "high": c,
        "low": c,
        "close": c,
    }


def view(
    meta: SeriesMetadata, aux_days: list[int], kind: str, ts: np.ndarray, lag: int, stale: int
) -> AuxView:
    return build_view(
        meta, aux_arrays(aux_days), traded_meta(kind), ts,
        extra_lag_days=lag, max_stale_sessions=stale, sessions_file=SESSIONS,
    )  # fmt: skip


@st.composite
def cases(draw: st.DrawFn) -> dict[str, Any]:
    kind = draw(st.sampled_from(sorted(TRADED)))
    pool = NYSE_DAYS if kind.startswith("equity") else WEEKDAYS
    start = draw(st.integers(0, len(pool) - 40))
    traded_days = pool[start : start + draw(st.integers(5, 30))]
    aux_pool = [d for d in WEEKDAYS if traded_days[0] - 20 <= d <= traded_days[-1] + 5]
    keep = draw(st.lists(st.booleans(), min_size=len(aux_pool), max_size=len(aux_pool)))
    aux_days = [d for d, k in zip(aux_pool, keep, strict=True) if k]
    return {
        "kind": kind,
        "traded_days": traded_days,
        "aux_days": aux_days or aux_pool[:1],
        "close": draw(st.sampled_from(CLOSES)),
        "zone": draw(st.sampled_from(["America/New_York", "America/Chicago"])),
        "lag": draw(st.integers(0, 2)),
        "stale": draw(st.integers(0, 6)),
        "cut": draw(st.floats(0.0, 1.0)),
    }


@settings(max_examples=examples(150), deadline=None)
@given(cases())
def test_F_0_1_11_no_bar_reads_a_value_not_yet_final(c: dict[str, Any]) -> None:
    meta = aux_meta(c["close"], c["zone"])
    ts = traded_ts(c["kind"], c["traded_days"])
    v = view(meta, c["aux_days"], c["kind"], ts, c["lag"], c["stale"])
    ok = v.idx >= 0
    assert (v.final_us[v.idx[ok]] < v.decision_us[ok]).all()
    assert (v.decision_us > ts).all()  # the decision is the bar's end, never its start
    assert v.final_us.size == 0 or int(v.final_us.max()) < int(v.decision_us.max())


@settings(max_examples=examples(150), deadline=None)
@given(cases())
def test_F_0_1_11_truncating_the_future_changes_nothing(c: dict[str, Any]) -> None:
    """Cut the aux series after T and the traded bars after bar k: every bar decided by T reads
    the same aux value (the same date) as with the full data."""
    meta = aux_meta(c["close"], c["zone"])
    ts = traded_ts(c["kind"], c["traded_days"])
    full = view(meta, c["aux_days"], c["kind"], ts, c["lag"], c["stale"])
    k = max(1, int(c["cut"] * ts.size))
    t_cut = int(full.decision_us[k - 1])  # T = the decision instant of bar k-1
    known = [d for d, f in zip(c["aux_days"], _finals(meta, c["aux_days"], c["lag"]), strict=True)
             if f < t_cut]  # fmt: skip
    if not known:
        return
    cut = view(meta, known, c["kind"], ts[:k], c["lag"], c["stale"])
    a = full.at_bars(full.close)[:k]
    b = cut.at_bars(cut.close)
    assert np.array_equal(a, b, equal_nan=True)


def _finals(meta: SeriesMetadata, days: list[int], lag: int) -> np.ndarray:
    from strategy_factory.data.auxiliary import final_instants

    return final_instants(np.array(days, dtype=np.int64) * US_DAY, meta, lag)
