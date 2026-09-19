"""Shared helpers for the Alpaca tests (fixtures, config, fake client)."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from strategy_factory.data.config import (
    AlpacaConfig,
    HourlySessionConfig,
    RetryConfig,
    SplitCheckConfig,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "alpaca"


def load_fixture(name: str) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = json.loads(
        (FIXTURES / name).read_text(encoding="utf-8")
    )
    return data


def make_config(**overrides: Any) -> AlpacaConfig:
    """Config with absolute paths to the repo's calendar and known-splits files."""
    base: dict[str, Any] = {
        "hourly_session": HourlySessionConfig(
            early_closes_file=REPO / "configs" / "calendars" / "nyse_early_closes.yaml"
        ),
        "split_check": SplitCheckConfig(
            known_splits_file=REPO / "configs" / "data" / "known_splits.csv"
        ),
        "retry": RetryConfig(max_retries=3, backoff_base_seconds=1.0, backoff_max_seconds=8.0),
        "batch_size": {"1D": 2, "1H": 2},
    }
    base.update(overrides)
    return AlpacaConfig(**base)


class FakeClient:
    """BarsClient serving fixture bars filtered to the requested window."""

    def __init__(
        self, bars: dict[str, list[dict[str, Any]]], failures: list[Exception] | None = None
    ) -> None:
        self.bars = bars
        self.failures = list(failures or [])
        self.calls: list[tuple[tuple[str, ...], str, dt.datetime, dt.datetime]] = []

    @property
    def library_version(self) -> str:
        return "fake 0"

    def get_bars(
        self, symbols: Sequence[str], timeframe: str, start: dt.datetime, end: dt.datetime
    ) -> dict[str, list[dict[str, Any]]]:
        self.calls.append((tuple(symbols), timeframe, start, end))
        if self.failures:
            raise self.failures.pop(0)
        out: dict[str, list[dict[str, Any]]] = {}
        for s in symbols:
            rows = [
                b
                for b in self.bars.get(s, [])
                if start <= dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")) <= end
            ]
            if rows:
                out[s] = rows
        return out
