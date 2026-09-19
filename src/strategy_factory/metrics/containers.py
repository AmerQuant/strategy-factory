"""Result containers: the contract between engine (T08), metrics, gates and reports.

The engine produces one :class:`RunResult` per backtest: a :class:`TradeLog` (one row per
closed trade), an :class:`EquityCurve` (one row per bar) and :class:`RunMeta`. All arrays are
NumPy, read-only after construction, and validated on construction (violations raise
:class:`ContainerError`).

Conventions (see CLAUDE.md, design §6):

* ``ts`` is ``datetime64[ns]``, UTC, bar-start, strictly increasing.
* Bar indices refer to rows of the :class:`EquityCurve` of the same run.
* ``entry_idx`` is the bar at whose **open** the entry fills (the signal bar is
  ``entry_idx - 1``); ``exit_idx`` is the bar in which the exit fills (at its open or
  intrabar). ``exit_idx >= entry_idx + 1`` and ``bars_held = exit_idx - entry_idx``.
* ``in_position[t]`` is True when a position is held at the **close** of bar ``t``, i.e.
  ``equity_mtm[t]`` includes open P&L. A trade occupies bars ``entry_idx .. exit_idx - 1``.
* Money is in account currency (USD). Costs are non-negative amounts that are subtracted:
  ``pnl_net = pnl_gross - (cost_spread + cost_slippage + cost_commission + cost_swap)``
  (a swap *credit* is a negative ``cost_swap``).
* ``mae`` / ``mfe`` are non-negative money amounts (maximum adverse / favourable excursion
  of the open trade, ``qty x price distance``).
* ``realized_pnl[t]`` is the cumulative ``pnl_net`` of trades closed up to bar ``t``;
  ``open_pnl_end`` is the marked P&L of a position still open at the last bar (0 when flat).
  Final equity must equal ``initial_capital + sum(pnl_net) + open_pnl_end``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import IntEnum
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from strategy_factory.core.errors import SfacError

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]
TsArray = NDArray[np.datetime64]

# Float-equality tolerance for the money identities, relative to initial capital. This is a
# numerical round-off allowance, not a decision threshold.
MONEY_RTOL = 1e-9


class ContainerError(SfacError):
    """A result container violates the engine output contract."""


class ExitReason(IntEnum):
    """Exit reason codes stored in ``TradeLog.exit_reason``. Codes are append-only."""

    SIGNAL = 0
    STOP_LOSS = 1
    TAKE_PROFIT = 2
    DISASTER_STOP = 3
    TIME_EXIT = 4


def _frozen_array(value: Any, dtype: Any, name: str) -> NDArray[Any]:
    arr = np.array(value, dtype=dtype, copy=True)
    if arr.ndim != 1:
        raise ContainerError(f"{name} must be 1-D, got shape {arr.shape}")
    arr.setflags(write=False)
    return arr


def _ts_array(value: Any, name: str) -> TsArray:
    arr = np.asarray(value)
    if not np.issubdtype(arr.dtype, np.datetime64):
        raise ContainerError(f"{name} must be datetime64 (UTC), got {arr.dtype}")
    return _frozen_array(arr.astype("datetime64[ns]"), "datetime64[ns]", name)


def _check_strictly_increasing(ts: TsArray, name: str) -> None:
    if ts.size > 1 and not bool(np.all(np.diff(ts.view(np.int64)) > 0)):
        raise ContainerError(f"{name} must be strictly increasing")


def _money_tol(capital: float) -> float:
    return MONEY_RTOL * max(1.0, abs(capital))


_TRADE_FLOAT = (
    "qty",
    "entry_price",
    "exit_price",
    "pnl_gross",
    "cost_spread",
    "cost_slippage",
    "cost_commission",
    "cost_swap",
    "pnl_net",
    "mae",
    "mfe",
    "atr_at_entry",
)
_TRADE_INT = ("entry_idx", "exit_idx", "direction", "exit_reason", "bars_held")


@dataclass(frozen=True, eq=False)
class TradeLog:
    """Columnar log of closed trades (one row per trade, ordered by ``entry_idx``)."""

    entry_idx: IntArray
    exit_idx: IntArray
    entry_ts: TsArray
    exit_ts: TsArray
    direction: IntArray
    qty: FloatArray
    entry_price: FloatArray
    exit_price: FloatArray
    pnl_gross: FloatArray
    cost_spread: FloatArray
    cost_slippage: FloatArray
    cost_commission: FloatArray
    cost_swap: FloatArray
    pnl_net: FloatArray
    exit_reason: IntArray
    mae: FloatArray
    mfe: FloatArray
    atr_at_entry: FloatArray
    bars_held: IntArray

    def __post_init__(self) -> None:
        for name in _TRADE_FLOAT:
            object.__setattr__(self, name, _frozen_array(getattr(self, name), np.float64, name))
        for name in _TRADE_INT:
            object.__setattr__(self, name, _frozen_array(getattr(self, name), np.int64, name))
        for name in ("entry_ts", "exit_ts"):
            object.__setattr__(self, name, _ts_array(getattr(self, name), name))
        self._validate()

    def __len__(self) -> int:
        return int(self.entry_idx.size)

    @classmethod
    def empty(cls) -> TradeLog:
        cols: dict[str, Any] = {f.name: np.empty(0, dtype=np.float64) for f in fields(cls)}
        for name in _TRADE_INT:
            cols[name] = np.empty(0, dtype=np.int64)
        cols["entry_ts"] = np.empty(0, dtype="datetime64[ns]")
        cols["exit_ts"] = np.empty(0, dtype="datetime64[ns]")
        return cls(**cols)

    @property
    def total_costs(self) -> FloatArray:
        return self.cost_spread + self.cost_slippage + self.cost_commission + self.cost_swap

    def columns(self) -> dict[str, NDArray[Any]]:
        """All columns by name, in field order."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def _validate(self) -> None:
        n = self.entry_idx.size
        for f in fields(self):
            if getattr(self, f.name).size != n:
                raise ContainerError(f"TradeLog column {f.name} has length != {n}")
        if n == 0:
            return
        for name in _TRADE_FLOAT:
            if not bool(np.all(np.isfinite(getattr(self, name)))):
                raise ContainerError(f"TradeLog.{name} contains non-finite values")
        if bool(np.any(self.entry_idx < 0)):
            raise ContainerError("TradeLog.entry_idx must be >= 0")
        if bool(np.any(self.exit_idx < self.entry_idx + 1)):
            raise ContainerError("TradeLog: exit_idx must be >= entry_idx + 1")
        if bool(np.any(self.bars_held != self.exit_idx - self.entry_idx)):
            raise ContainerError("TradeLog: bars_held must equal exit_idx - entry_idx")
        if n > 1 and bool(np.any(self.entry_idx[1:] < self.exit_idx[:-1])):
            raise ContainerError("TradeLog: trades overlap or are not ordered (one position)")
        if not bool(np.all(np.isin(self.direction, (1, -1)))):
            raise ContainerError("TradeLog.direction must be +1 or -1")
        if bool(np.any(self.qty <= 0)):
            raise ContainerError("TradeLog.qty must be > 0")
        if bool(np.any(self.entry_price <= 0)) or bool(np.any(self.exit_price <= 0)):
            raise ContainerError("TradeLog prices must be > 0")
        if bool(np.any(self.atr_at_entry <= 0)):
            raise ContainerError("TradeLog.atr_at_entry must be > 0")
        for name in ("cost_spread", "cost_slippage", "cost_commission", "mae", "mfe"):
            if bool(np.any(getattr(self, name) < 0)):
                raise ContainerError(f"TradeLog.{name} must be >= 0")
        valid_reasons = [int(r) for r in ExitReason]
        if not bool(np.all(np.isin(self.exit_reason, valid_reasons))):
            raise ContainerError("TradeLog.exit_reason has an unknown code")
        if bool(np.any(self.exit_ts <= self.entry_ts)):
            raise ContainerError("TradeLog: exit_ts must be after entry_ts")
        expected = self.pnl_gross - self.total_costs
        tol = MONEY_RTOL * np.maximum(1.0, np.abs(self.pnl_gross) + self.total_costs)
        if bool(np.any(np.abs(self.pnl_net - expected) > tol)):
            raise ContainerError("TradeLog: pnl_net must equal pnl_gross minus all costs")


@dataclass(frozen=True, eq=False)
class EquityCurve:
    """Mark-to-market equity at every bar close."""

    ts: TsArray
    equity_mtm: FloatArray
    in_position: BoolArray
    realized_pnl: FloatArray
    initial_capital: float
    notional: float
    open_pnl_end: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "ts", _ts_array(self.ts, "ts"))
        object.__setattr__(self, "equity_mtm", _frozen_array(self.equity_mtm, np.float64, "eq"))
        object.__setattr__(self, "in_position", _frozen_array(self.in_position, np.bool_, "pos"))
        object.__setattr__(
            self, "realized_pnl", _frozen_array(self.realized_pnl, np.float64, "realized")
        )
        object.__setattr__(self, "initial_capital", float(self.initial_capital))
        object.__setattr__(self, "notional", float(self.notional))
        object.__setattr__(self, "open_pnl_end", float(self.open_pnl_end))
        self._validate()

    def __len__(self) -> int:
        return int(self.ts.size)

    def _validate(self) -> None:
        n = self.ts.size
        if n < 2:
            raise ContainerError("EquityCurve needs at least 2 bars")
        for name in ("equity_mtm", "in_position", "realized_pnl"):
            if getattr(self, name).size != n:
                raise ContainerError(f"EquityCurve.{name} has length != len(ts)")
        _check_strictly_increasing(self.ts, "EquityCurve.ts")
        if not bool(np.all(np.isfinite(self.equity_mtm))):
            raise ContainerError("EquityCurve.equity_mtm contains non-finite values")
        if not bool(np.all(np.isfinite(self.realized_pnl))):
            raise ContainerError("EquityCurve.realized_pnl contains non-finite values")
        for name in ("initial_capital", "notional", "open_pnl_end"):
            if not np.isfinite(getattr(self, name)):
                raise ContainerError(f"EquityCurve.{name} must be finite")
        if self.initial_capital <= 0 or self.notional <= 0:
            raise ContainerError("EquityCurve initial_capital and notional must be > 0")
        tol = _money_tol(self.initial_capital)
        flat = ~self.in_position
        flat_gap = self.equity_mtm[flat] - (self.initial_capital + self.realized_pnl[flat])
        if bool(np.any(np.abs(flat_gap) > tol)):
            raise ContainerError("EquityCurve: flat bars must have equity = capital + realized")
        if not bool(self.in_position[-1]) and self.open_pnl_end != 0.0:
            raise ContainerError("EquityCurve: open_pnl_end must be 0 when flat at the end")
        end = self.initial_capital + self.realized_pnl[-1] + self.open_pnl_end
        if abs(self.equity_mtm[-1] - end) > tol:
            raise ContainerError(
                "EquityCurve: final equity must equal capital + realized + open_pnl_end"
            )

    @property
    def open_position_marked(self) -> bool:
        """True when a position is still open at the last bar (its P&L is marked, not closed)."""
        return bool(self.in_position[-1])


CostStatus = Literal["placeholder", "verified"]
IntrabarMode = Literal["tradingview", "pessimistic"]


class RunMeta(BaseModel):
    """Identification of one run (what was simulated and under which assumptions)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    timeframe: str
    spec_hash: str
    cost_status: CostStatus
    intrabar_mode: IntrabarMode
    stress: str | None = None


@dataclass(frozen=True, eq=False)
class RunResult:
    """Engine output of one run. Cross-validated: trades must be consistent with the curve."""

    trades: TradeLog
    equity: EquityCurve
    meta: RunMeta

    def __post_init__(self) -> None:
        self._validate()

    @property
    def open_position_marked(self) -> bool:
        return self.equity.open_position_marked

    def _validate(self) -> None:
        tr, eq = self.trades, self.equity
        n = len(eq)
        if len(tr) > 0:
            if int(tr.exit_idx.max()) > n - 1:
                raise ContainerError("RunResult: trade exit_idx beyond the equity curve")
            if bool(np.any(tr.entry_ts != eq.ts[tr.entry_idx])):
                raise ContainerError("RunResult: entry_ts must equal ts[entry_idx]")
            if bool(np.any(tr.exit_ts != eq.ts[tr.exit_idx])):
                raise ContainerError("RunResult: exit_ts must equal ts[exit_idx]")
        self._validate_positions()
        tol = _money_tol(eq.initial_capital)
        total_net = float(np.sum(tr.pnl_net)) if len(tr) else 0.0
        if abs(eq.realized_pnl[-1] - total_net) > tol:
            raise ContainerError("RunResult: realized_pnl at the end must equal sum(pnl_net)")
        end = eq.initial_capital + total_net + eq.open_pnl_end
        if abs(eq.equity_mtm[-1] - end) > tol:
            raise ContainerError(
                "RunResult: final equity must equal capital + sum(pnl_net) + open P&L"
            )

    def _validate_positions(self) -> None:
        """``in_position`` must be True exactly on the bars occupied by trades.

        A closed trade occupies bars ``entry_idx .. exit_idx - 1``; a position still open at
        the end occupies the final run of True bars, which must start at or after the last
        exit.
        """
        tr, eq = self.trades, self.equity
        n = len(eq)
        marks = np.zeros(n + 1, dtype=np.int64)
        np.add.at(marks, tr.entry_idx, 1)
        np.add.at(marks, tr.exit_idx, -1)
        expected = np.cumsum(marks[:n]) > 0
        if eq.open_position_marked:
            flat_idx = np.flatnonzero(~eq.in_position)
            start = int(flat_idx[-1]) + 1 if flat_idx.size else 0
            last_exit = int(tr.exit_idx.max()) if len(tr) else 0
            if start < last_exit:
                raise ContainerError("RunResult: open position at the end overlaps a closed trade")
            expected[start:] = True
        if not bool(np.array_equal(expected, eq.in_position)):
            raise ContainerError("RunResult: in_position does not match the trade log")
