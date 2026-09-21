"""Trade-by-trade comparison against TradingView (T11 §4, F-0.3.8, D-011).

Matching
--------
Engine trades and TradingView trades are paired on **(direction, entry bar)**. The entry bar is
the bar the fill is stamped on: TradingView writes the *fill* bar, and so does the engine's
``entry_idx``. A daily reference carries no time of day, so its rows are matched by **date**
(:meth:`ChartData.index_on_date`); an intraday one by the exact stamp.

What is compared, and what is excluded
--------------------------------------
* Only trades whose entry falls inside the **range the TradingView trade list covers**
  (D-363): a reference's OHLC starts long before its first trade.
* The **open position at the end is excluded on both sides** (supervisor note 2): TradingView
  reports it with placeholder cells, the engine may hold one at the last bar, and neither is a
  closed trade.

Reasons
-------
Every unmatched or differing trade is classified, so a difference report says *why* rather
than just *how many*. The reasons are the known ambiguities of D-327, D-335, D-336, D-349 and
the two HANDOFF §8 notes, plus ``sub_tick_level``: both Pine scripts pass stop and target
distances as **ticks** (``math.round(k * atr / syminfo.mintick)``) while the engine keeps the
level unrounded, so a stop can trigger one bar earlier or later. An unclassifiable difference
is reported as ``unexplained`` -- never quietly dropped.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

import numpy as np

from strategy_factory.engine import kernel as k
from strategy_factory.metrics.containers import RunResult
from strategy_factory.selftest.parity_refs import ChartData, TradeList, TradeRow

#: Every reason a pair can get. ``rollover_swap``, ``trailing_at_close`` and
#: ``conversion_rate`` are the task's named ambiguities (T11 §4) but **cannot occur in a
#: TradingView parity run** (D-371: TradingView models no swap, neither reference trails, both
#: are USD-quoted), so this classifier never assigns them; they stay named so a future
#: reference that could produce one has a place to put it.
Reason = Literal[
    "match",
    "sub_tick_level",
    "atr_warm_up",
    "intrabar_path",
    "same_open_reentry",
    "rollover_swap",
    "trailing_at_close",
    "conversion_rate",
    "quantity",
    "missing_in_engine",
    "extra_in_engine",
    "unexplained",
]


@dataclass(frozen=True)
class TradePair:
    """One TradingView trade and the engine trade matched to it (either may be absent)."""

    tv_index: int | None
    engine_index: int | None
    direction: int
    entry_bar: int | None
    reason: Reason
    detail: str = ""
    tv_entry: float | None = None
    tv_exit: float | None = None
    engine_entry: float | None = None
    engine_exit: float | None = None
    tv_pnl: float | None = None
    engine_pnl: float | None = None

    @property
    def matched(self) -> bool:
        return self.reason == "match"


@dataclass(frozen=True)
class Comparison:
    """The result of comparing one reference."""

    pairs: tuple[TradePair, ...]
    tv_trades: int
    engine_trades: int
    tv_net_profit: float
    engine_net_profit: float
    excluded_open_tv: tuple[int, ...] = ()
    excluded_open_engine: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def matched(self) -> int:
        return sum(1 for p in self.pairs if p.matched)

    @property
    def matched_share(self) -> float:
        """Matched trades over the TradingView trade count -- D-011's "share of trades"."""
        return self.matched / self.tv_trades if self.tv_trades else 0.0

    def by_reason(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self.pairs:
            out[p.reason] = out.get(p.reason, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    def differences(self) -> list[TradePair]:
        return [p for p in self.pairs if not p.matched]


def tv_entry_bar(chart: ChartData, row: TradeRow, daily: bool) -> int | None:
    """The chart bar a TradingView trade row is stamped on; ``None`` when it is not a bar."""
    from strategy_factory.core.errors import DataError

    try:
        return chart.index_on_date(row.when) if daily else chart.index_of(row.when)
    except DataError:
        return None


def export_decimals(tick: float) -> int:
    """Decimals TradingView writes for a symbol with this tick size (0.01 -> 2)."""
    text = f"{tick:.10f}".rstrip("0")
    return max(0, len(text.split(".")[1])) if "." in text else 0


def round_like_tradingview(value: float, decimals: int) -> float:
    """Round half **away from zero**, as TradingView's export does.

    Python's :func:`round` is round-half-to-even, so ``round(44.625, 2)`` is ``44.62`` while
    the export writes ``44.63``. Using the built-in here would invent a difference on every
    price that lands exactly on a half.
    """
    quantum = Decimal(1).scaleb(-decimals)
    return float(Decimal(repr(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def same_price(tv_price: float, engine_price: float, decimals: int) -> bool:
    """True when the engine's price rounds to what the export shows.

    The export rounds: TradingView writes ``44.88`` for a SPY price of ``44.875``. Comparing
    the raw numbers would call that a difference, so the engine's price is rounded the same way
    before comparing. Anything that still differs is a real difference.
    """
    return round_like_tradingview(engine_price, decimals) == round_like_tradingview(
        tv_price, decimals
    )


def _price_reason(
    tv_price: float, engine_price: float, tick: float, within: float
) -> tuple[bool, float]:
    """``(is a sub-tick difference, difference in ticks)``."""
    ticks = abs(tv_price - engine_price) / tick if tick > 0 else float("inf")
    return ticks <= within, ticks


def compare(
    chart: ChartData,
    tv: TradeList,
    result: RunResult,
    *,
    tick_size: float,
    daily: bool,
    sub_tick_ticks: float,
    qty_step: float,
) -> Comparison:
    """Pair the engine's trades with TradingView's and classify every difference.

    Prices are compared **at the export's own precision** (:func:`same_price`): TradingView
    writes 2 decimals for SPY, so an engine price of 44.875 and an exported 44.88 are the same
    number, not a difference. Anything that still differs is real and is classified, never
    silently accepted.
    """
    tv_pairs = tv.trades()
    covered = {
        t: i
        for i, (e, _) in enumerate(tv_pairs)
        if (t := tv_entry_bar(chart, e, daily)) is not None
    }
    trades = result.trades
    engine_by_bar: dict[int, int] = {}
    duplicates: list[int] = []
    for i, bar in enumerate(trades.entry_idx.tolist()):
        if bar in engine_by_bar:
            duplicates.append(int(bar))
        engine_by_bar[int(bar)] = i

    first_bar = min(covered, default=0)
    last_bar = max(covered, default=len(chart) - 1)
    pairs: list[TradePair] = []
    used: set[int] = set()

    for bar, tv_i in sorted(covered.items()):
        tv_entry, tv_exit = tv_pairs[tv_i]
        engine_i = engine_by_bar.get(bar)
        if engine_i is None:
            reason: Reason = "atr_warm_up" if bar < chart.atr_warm_up_bars else "missing_in_engine"
            pairs.append(
                TradePair(
                    tv_index=tv_i,
                    engine_index=None,
                    direction=tv_entry.direction,
                    entry_bar=bar,
                    reason=reason,
                    detail="no engine trade entered on this bar",
                    tv_entry=tv_entry.price,
                    tv_exit=tv_exit.price,
                    tv_pnl=tv_exit.pnl,
                )
            )
            continue
        used.add(engine_i)
        pairs.append(
            _classify(
                tv_i,
                engine_i,
                tv_entry,
                tv_exit,
                trades,
                chart,
                bar,
                tick_size,
                sub_tick_ticks,
                daily,
                qty_step,
            )
        )

    exits = trades.exit_idx.tolist()
    for i, bar in enumerate(trades.entry_idx.tolist()):
        if i in used or not (first_bar <= bar <= last_bar):
            continue  # outside the range the TV list covers (D-363)
        reentry = i > 0 and exits[i - 1] == bar
        pairs.append(
            TradePair(
                tv_index=None,
                engine_index=i,
                direction=int(trades.direction[i]),
                entry_bar=int(bar),
                reason="same_open_reentry" if reentry else "extra_in_engine",
                detail=(
                    "the engine re-entered at the open where its previous trade exited (D-336)"
                    if reentry
                    else "the engine entered where TradingView did not"
                ),
                engine_entry=float(trades.entry_price[i]),
                engine_exit=float(trades.exit_price[i]),
                engine_pnl=float(trades.pnl_net[i]),
            )
        )

    notes: list[str] = []
    if duplicates:
        notes.append(f"{len(duplicates)} engine trades share an entry bar with another")
    return Comparison(
        pairs=tuple(sorted(pairs, key=lambda p: (p.entry_bar or 0, p.tv_index or 0))),
        tv_trades=len(covered),
        engine_trades=sum(1 for b in trades.entry_idx.tolist() if first_bar <= b <= last_bar),
        tv_net_profit=float(
            sum(x.pnl or 0.0 for i, (_, x) in enumerate(tv_pairs) if i in covered.values())
        ),
        engine_net_profit=float(
            sum(
                float(trades.pnl_net[i])
                for i, b in enumerate(trades.entry_idx.tolist())
                if first_bar <= b <= last_bar
            )
        ),
        excluded_open_tv=tuple(tv.open_trades()),
        # the flag lives on the run, not on its meta: a `hasattr` guard on `meta` here once hid
        # that and reported False for every run (found on the TF long reference)
        excluded_open_engine=result.open_position_marked,
        notes=tuple(notes),
    )


def _classify(
    tv_i: int,
    engine_i: int,
    tv_entry: TradeRow,
    tv_exit: TradeRow,
    trades: object,
    chart: ChartData,
    bar: int,
    tick: float,
    sub_tick_ticks: float,
    daily: bool,
    qty_step: float,
) -> TradePair:
    """One matched entry bar: same trade, or a classified difference.

    The quantity is compared too, to half a quantity step: the prices and bars can agree while
    the size does not, and without this a sizing difference is called a match and shows up
    only in the net profit (found on MR: 5 trades one share off, T11 review §7).
    """
    t = trades
    engine_entry = float(t.entry_price[engine_i])  # type: ignore[attr-defined]
    engine_exit = float(t.exit_price[engine_i])  # type: ignore[attr-defined]
    engine_dir = int(t.direction[engine_i])  # type: ignore[attr-defined]
    engine_exit_bar = int(t.exit_idx[engine_i])  # type: ignore[attr-defined]
    engine_pnl = float(t.pnl_net[engine_i])  # type: ignore[attr-defined]
    common = {
        "tv_index": tv_i,
        "engine_index": engine_i,
        "direction": tv_entry.direction,
        "entry_bar": bar,
        "tv_entry": tv_entry.price,
        "tv_exit": tv_exit.price,
        "engine_entry": engine_entry,
        "engine_exit": engine_exit,
        "tv_pnl": tv_exit.pnl,
        "engine_pnl": engine_pnl,
    }
    if engine_dir != tv_entry.direction:
        return TradePair(reason="unexplained", detail="opposite direction", **common)  # type: ignore[arg-type]

    tv_exit_bar = tv_entry_bar(chart, tv_exit, daily)
    decimals = export_decimals(tick)
    same_entry = same_price(tv_entry.price, engine_entry, decimals)
    same_exit = same_price(tv_exit.price, engine_exit, decimals)
    same_exit_bar = tv_exit_bar is None or tv_exit_bar == engine_exit_bar

    if same_entry and same_exit and same_exit_bar:
        engine_qty = float(t.qty[engine_i])  # type: ignore[attr-defined]
        # quantities are whole steps, so half a step apart means a different number of steps
        if abs(tv_entry.quantity - engine_qty) >= qty_step / 2:
            return TradePair(
                reason="quantity",
                detail=f"quantity {tv_entry.quantity:g} vs engine {engine_qty:g}",
                **common,  # type: ignore[arg-type]
            )
        return TradePair(reason="match", **common)  # type: ignore[arg-type]

    if not same_entry:
        sub_tick, ticks = _price_reason(tv_entry.price, engine_entry, tick, sub_tick_ticks)
        return TradePair(
            reason="sub_tick_level" if sub_tick else "unexplained",
            detail=f"entry price differs by {ticks:.2f} ticks",
            **common,  # type: ignore[arg-type]
        )

    sub_tick, ticks = _price_reason(tv_exit.price, engine_exit, tick, sub_tick_ticks)
    if sub_tick:
        # a level one tick away: the same decision, rounded differently (D-366). On another
        # bar too -- a stop one tick lower can be touched a bar later.
        where = "" if same_exit_bar else f", exit bar {engine_exit_bar} vs {tv_exit_bar}"
        return TradePair(
            reason="sub_tick_level",
            detail=f"exit price differs by {ticks:.2f} ticks{where}",
            **common,  # type: ignore[arg-type]
        )
    engine_reason = int(t.exit_reason[engine_i])  # type: ignore[attr-defined]
    if same_exit_bar and engine_reason in LEVEL_EXITS:
        # D-335: the bar touched two levels and the two sides took different ones -- the only
        # difference an intrabar path choice can make is WHICH level, on the SAME bar
        return TradePair(
            reason="intrabar_path",
            detail=f"same exit bar, price differs by {ticks:.2f} ticks (a level choice)",
            **common,  # type: ignore[arg-type]
        )
    return TradePair(
        reason="unexplained",
        detail=(
            f"exit bar {engine_exit_bar} vs {tv_exit_bar}, price differs by {ticks:.2f} ticks"
            if not same_exit_bar
            else f"exit price differs by {ticks:.2f} ticks on a non-level exit"
        ),
        **common,  # type: ignore[arg-type]
    )


#: The engine exits that happen AT a price level inside a bar -- the only ones an intrabar
#: path choice (D-335) can affect. Signal and time exits fill at the next open.
LEVEL_EXITS = frozenset({k.STOP_LOSS, k.TAKE_PROFIT, k.DISASTER_STOP, k.TRAILING_STOP})


def difference_table(comparison: Comparison, limit: int = 20) -> list[str]:
    """The difference report of F-0.3.8: a reason per mismatch."""
    lines = [
        f"matched {comparison.matched}/{comparison.tv_trades} "
        f"({comparison.matched_share:.2%}); engine trades in range: {comparison.engine_trades}",
        "reasons: " + ", ".join(f"{k} {v}" for k, v in comparison.by_reason().items()),
    ]
    if comparison.excluded_open_tv:
        lines.append(
            f"excluded: TradingView trade(s) {list(comparison.excluded_open_tv)} still open"
            + (", and the engine's open position" if comparison.excluded_open_engine else "")
        )
    for note in comparison.notes:
        lines.append(f"note: {note}")
    diffs = comparison.differences()
    if diffs:
        lines.append(f"{len(diffs)} difference(s); first {min(limit, len(diffs))}:")
        for p in diffs[:limit]:
            lines.append(
                f"  bar {p.entry_bar} dir {p.direction:+d} [{p.reason}] {p.detail}"
                f" | TV {p.tv_entry}->{p.tv_exit} vs engine {p.engine_entry}->{p.engine_exit}"
            )
    return lines


def atr_matches_tradingview(
    engine_atr: np.ndarray, golden_atr: np.ndarray, rtol: float = 1e-9
) -> tuple[bool, float, int]:
    """``(agrees, worst relative difference, compared bars)`` for Wilder's ATR.

    Supervisor note 3: the engine's ATR must equal Pine's ``ta.atr`` before a single trade is
    compared. A mismatch here is a **separate finding**, not a trade-matching reason.
    """
    both = np.isfinite(engine_atr) & np.isfinite(golden_atr)
    if not both.any():
        return False, float("inf"), 0
    a, b = engine_atr[both], golden_atr[both]
    worst = float(np.max(np.abs(a - b) / np.maximum(np.abs(b), 1e-12)))
    return worst <= rtol, worst, int(both.sum())


def covered_range_bars(chart: ChartData, tv: TradeList, daily: bool) -> tuple[int, int]:
    """First and last chart bar the TradingView trade list covers (D-363)."""
    lo, hi = tv.covered_range()
    first = chart.index_on_date(lo) if daily else chart.index_of(lo)
    last = chart.index_on_date(hi) if daily else chart.index_of(hi)
    return first, last


def as_datetimes(chart: ChartData, bars: Sequence[int]) -> list[dt.datetime]:
    return [dt.datetime.fromtimestamp(int(chart.ts[b]), dt.UTC) for b in bars]
