"""``SyntheticDataAccess``: the stages' bars, replaced by a synthetic universe (D-654, D-670).

A :class:`~strategy_factory.data.split.DataAccess` whose ``arrays(symbol, timeframe)`` returns the
synthetic version of the real **development** bars: the calibrated null (``kind: null``) or the
null with the symbol's planted cell (``kind: planted``). It is generated in memory,
deterministically from (the source seed, symbol, timeframe), every time it is asked for -- stages
1, 2 and 3 see the same series -- and **never written to the store** (``SFAC_DATA_ROOT`` is
stream B's). The split boundaries, splices and cost inputs stay the real symbol's.

The stages are unchanged: they take their bars from ``ctx.data``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl

from strategy_factory.core.config import SourceRef
from strategy_factory.core.errors import ConfigError
from strategy_factory.data.split import DataAccess, SplitManager
from strategy_factory.pipeline.executor import unit_seed
from strategy_factory.synthetic.config import NullConfig, PlantedConfig, parse_cell
from strategy_factory.synthetic.null import null_bars
from strategy_factory.synthetic.planted import Truth, plant

Bars = dict[str, npt.NDArray[Any]]


def null_config_of(source: SourceRef) -> NullConfig:
    if source.kind == "null":
        return NullConfig.model_validate(source.generator)
    return PlantedConfig.model_validate(source.generator).base


def synthetic_series(
    source: SourceRef, symbol: str, timeframe: str, real: Bars
) -> tuple[Bars, Truth]:
    """The synthetic series of ``real`` (development bars) under ``source``, with its truth."""
    null = null_bars(
        real,
        timeframe,
        null_config_of(source),
        unit_seed(source.seed, f"{symbol}|{timeframe}|null"),
    )
    if source.kind == "null":
        return null, Truth(cell="null")
    cfg = PlantedConfig.model_validate(source.generator)
    if symbol not in cfg.assignment:
        raise ConfigError(f"planted source has no assignment for {symbol} (D-665)")
    cell = parse_cell(cfg.assignment[symbol])
    return plant(null, cell, cfg, timeframe, unit_seed(source.seed, f"{symbol}|{timeframe}|plant"))


class SyntheticDataAccess(DataAccess):
    """Development bars of the synthetic universe ``source`` (see the module docstring)."""

    def __init__(self, splits: SplitManager, source: SourceRef) -> None:
        super().__init__(splits)
        self.source = source

    def real_arrays(self, symbol: str, timeframe: str) -> Bars:
        """The real development bars (``DataAccess``'s, not this class's ``bars``)."""
        df = DataAccess.bars(self, symbol, timeframe)
        out: Bars = {c: df[c].to_numpy() for c in df.columns if c != "ts"}
        out["ts"] = df["ts"].dt.epoch("us").to_numpy()
        return out

    def arrays(self, symbol: str, timeframe: str) -> dict[str, np.ndarray[Any, Any]]:
        bars, _ = synthetic_series(
            self.source, symbol, timeframe, self.real_arrays(symbol, timeframe)
        )
        return bars

    def truth(self, symbol: str, timeframe: str) -> tuple[Truth, npt.NDArray[np.int64]]:
        real = self.real_arrays(symbol, timeframe)
        _, truth = synthetic_series(self.source, symbol, timeframe, real)
        return truth, np.asarray(real["ts"], dtype=np.int64)

    def bars(self, symbol: str, timeframe: str) -> pl.DataFrame:
        arrays = self.arrays(symbol, timeframe)
        ts = pl.Series("ts", arrays["ts"]).cast(pl.Datetime("us", "UTC"))
        cols = {k: v for k, v in arrays.items() if k != "ts"}
        return pl.DataFrame(cols).insert_column(0, ts)

    def aux(self, aux_symbol: str, traded_symbol: str, timeframe: str) -> Any:
        raise ConfigError("synthetic runs take no auxiliary series (D-654)")

    def conversion_bars(self, pair: str, traded_symbol: str, timeframe: str) -> Any:
        raise ConfigError("synthetic runs take no conversion series (D-654)")
