"""Parquet round-trip of a :class:`RunResult` (artifacts of candidates that pass a gate).

Layout of one artifact directory (written once, never overwritten)::

    trades.parquet   one row per closed trade (TradeLog columns)
    equity.parquet   ts, equity_mtm, in_position, realized_pnl
    meta.json        RunMeta, initial_capital, notional, open_pnl_end, schema_version

``ts`` columns are stored as naive ``Datetime(ns)`` holding UTC. Polars is used only as the
Parquet codec at this I/O boundary; arrays enter and leave as NumPy.
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from strategy_factory.metrics.containers import EquityCurve, RunMeta, RunResult, TradeLog

SCHEMA_VERSION = 1
_TRADES = "trades.parquet"
_EQUITY = "equity.parquet"
_META = "meta.json"


def write_run_result(result: RunResult, directory: Path) -> Path:
    """Write ``result`` into a new directory; raises if it already holds an artifact."""
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"artifact directory is not empty: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(result.trades.columns()).write_parquet(directory / _TRADES)
    eq = result.equity
    pl.DataFrame(
        {
            "ts": eq.ts,
            "equity_mtm": eq.equity_mtm,
            "in_position": eq.in_position,
            "realized_pnl": eq.realized_pnl,
        }
    ).write_parquet(directory / _EQUITY)
    meta: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "meta": result.meta.model_dump(mode="json"),
        "initial_capital": eq.initial_capital,
        "notional": eq.notional,
        "open_pnl_end": eq.open_pnl_end,
    }
    (directory / _META).write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    return directory


def _col(df: pl.DataFrame, name: str) -> np.ndarray:
    series = df.get_column(name)
    if series.dtype == pl.Datetime:
        return series.cast(pl.Datetime("ns")).to_numpy().astype("datetime64[ns]")
    return series.to_numpy()


def read_run_result(directory: Path) -> RunResult:
    """Read an artifact written by :func:`write_run_result` (re-validates the contract)."""
    directory = Path(directory)
    meta = json.loads((directory / _META).read_text(encoding="utf-8"))
    if meta.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported RunResult schema_version: {meta.get('schema_version')}")
    tdf = pl.read_parquet(directory / _TRADES)
    trades = TradeLog(**{f.name: _col(tdf, f.name) for f in fields(TradeLog)})
    edf = pl.read_parquet(directory / _EQUITY)
    equity = EquityCurve(
        ts=_col(edf, "ts"),
        equity_mtm=_col(edf, "equity_mtm"),
        in_position=_col(edf, "in_position"),
        realized_pnl=_col(edf, "realized_pnl"),
        initial_capital=meta["initial_capital"],
        notional=meta["notional"],
        open_pnl_end=meta["open_pnl_end"],
    )
    return RunResult(trades=trades, equity=equity, meta=RunMeta.model_validate(meta["meta"]))
