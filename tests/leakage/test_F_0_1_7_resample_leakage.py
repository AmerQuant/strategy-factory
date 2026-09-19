"""F-0.1.7 leakage: a resampled bar uses only the source bars inside its own period."""

from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl
import pytest
from fixtures.t05 import fx_bars, fx_meta
from hypothesis import given, settings
from hypothesis import strategies as st

from strategy_factory.data.config import QualityConfig, ResampleConfig
from strategy_factory.data.resample import resample_bars
from strategy_factory.data.schedule import period_start

pytestmark = pytest.mark.leakage

CFG, QCFG = ResampleConfig(), QualityConfig()
START = dt.datetime(2024, 1, 7, 22, tzinfo=dt.UTC)  # Sunday 17:00 New York
SOURCE = fx_bars(START, START + dt.timedelta(days=40), break_hour_ny=17, seed=7)
FULL = {
    (tf, mode): resample_bars(SOURCE, fx_meta(), tf, mode, CFG, QCFG).bars
    for tf in ("4H", "1D")
    for mode in ("research", "broker_session")
}


@settings(max_examples=40, deadline=None)
@given(
    cut=st.integers(min_value=30, max_value=SOURCE.height - 1),
    tf=st.sampled_from(["4H", "1D"]),
    mode=st.sampled_from(["research", "broker_session"]),
)
def test_F_0_1_7_truncation_invariance(cut: int, tf: str, mode: str) -> None:
    """Resampling data truncated at any bar reproduces every complete bar exactly."""
    part = resample_bars(SOURCE.head(cut), fx_meta(), tf, mode, CFG, QCFG).bars  # type: ignore[arg-type]
    full = FULL[(tf, mode)]
    joined = part.join(full, on="ts", how="left", suffix="_full")
    assert joined.height == part.height
    for col in ("open", "high", "low", "close", "volume", "spread"):
        if col in part.columns:
            assert joined[col].to_list() == joined[f"{col}_full"].to_list(), col


@settings(max_examples=25, deadline=None)
@given(
    k=st.integers(min_value=1, max_value=25),  # the 40-day source has ~30 daily bars
    mode=st.sampled_from(["research", "broker_session"]),
)
def test_F_0_1_7_later_source_bars_do_not_change_earlier_periods(k: int, mode: str) -> None:
    """Scaling every source bar of the periods after period k leaves bars 0..k unchanged."""
    full = FULL[("1D", mode)]
    boundary = full["ts"][k]
    period = SOURCE.select(
        period_start(pl.col("ts"), "1D", "fx", mode, CFG.broker_session)  # type: ignore[arg-type]
    ).to_series()
    later = (period > boundary).to_numpy()
    factor = np.where(later, np.random.default_rng(k).uniform(0.5, 1.5, SOURCE.height), 1.0)
    shaken = SOURCE.with_columns(
        [pl.col(c) * pl.Series(factor) for c in ("open", "high", "low", "close")]
    )
    out = resample_bars(shaken, fx_meta(), "1D", mode, CFG, QCFG).bars  # type: ignore[arg-type]
    assert out.filter(pl.col("ts") <= boundary).equals(full.filter(pl.col("ts") <= boundary))
    assert not out.filter(pl.col("ts") > boundary).equals(full.filter(pl.col("ts") > boundary))
