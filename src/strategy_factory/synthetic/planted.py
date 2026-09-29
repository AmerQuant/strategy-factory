"""The planted edge (D-654, D-665): the calibrated null plus an effect of known strength.

Measured before it was built (T15a plan §4, ``scripts/analysis/T15a_planted.py``). The edge is
**timing, never drift**:

* **MR** (``long``): events at seeded random bars, ``events_per_year`` on average. At an event
  bar the close is pushed down by ``s`` x ATR (the null's own ATR at the previous bar, as a
  fraction of price); over the next ``reversion_bars`` bars it reverts in equal steps. Net zero.
  ``short`` is the mirror: a spike up that reverts down.
* **TF** (``both``): segments of ``segment_bars`` starting at seeded random bars
  (``segments_per_year``); inside a segment each bar's return gains ``d`` x the bar volatility,
  the sign alternating from segment to segment (the first seeded), so the drift is ~unchanged and
  the edge is two-sided -- labelled so.

A planted run assigns every symbol of its scope to one cell (type, direction, strength) or to the
pure null, in equal shares (:func:`assign`), and records the planted positions per series
(:class:`Truth`) so a run can report which planted edges it found.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from strategy_factory.synthetic.config import Cell, PlantedConfig, cell_key

Floats = npt.NDArray[np.float64]
Bars = dict[str, npt.NDArray[Any]]


@dataclass(frozen=True)
class Truth:
    """What was planted in one series: the cell and its positions (bar indices)."""

    cell: str  # cell_key: "MR|long|2", "TF|both|0.3" or "null"
    events: tuple[int, ...] = ()  # MR: the event bars
    segments: tuple[tuple[int, int, int], ...] = field(default=())  # TF: (start, end, sign)

    def as_json(self, ts_us: npt.NDArray[np.int64]) -> dict[str, Any]:
        return {
            "cell": self.cell,
            "events": [int(ts_us[i]) for i in self.events],
            "segments": [
                {"start": int(ts_us[a]), "end": int(ts_us[b - 1]), "sign": s}
                for a, b, s in self.segments
            ],
        }


def assign(symbols: list[str], cfg: PlantedConfig, seed: int) -> dict[str, str]:
    """Every symbol to one cell or to the null, in equal shares, by a seeded permutation."""
    order = sorted(set(symbols))
    perm = np.random.default_rng(seed).permutation(len(order))
    shuffled = [order[i] for i in perm]
    n_null = round(len(order) * cfg.null_share)
    cells = cfg.cells()
    out: dict[str, str] = {}
    for i, sym in enumerate(shuffled):
        out[sym] = "null" if i < n_null else cell_key(cells[(i - n_null) % len(cells)])
    return out


def atr_fraction(bars: Bars, length: int) -> Floats:
    """ATR(length) / close known at each bar's previous close (NaN during the warm-up)."""
    h = np.asarray(bars["high"], dtype=np.float64)
    lo = np.asarray(bars["low"], dtype=np.float64)
    c = np.asarray(bars["close"], dtype=np.float64)
    n = c.size
    tr = np.empty(n)
    tr[0] = h[0] - lo[0]
    tr[1:] = np.maximum(h[1:] - lo[1:], np.maximum(abs(h[1:] - c[:-1]), abs(lo[1:] - c[:-1])))
    atr = np.full(n, np.nan)
    if n >= length:
        atr[length - 1 :] = np.convolve(tr, np.ones(length) / length, mode="valid")
    frac = atr / c
    return np.concatenate(([np.nan], frac[:-1]))


def _rebuild(null: Bars, add: Floats) -> Bars:
    """Add ``add`` (log) to each bar's body; the rest of the path shifts, bar shapes are kept."""
    cum = np.cumsum(add)
    lo0 = np.log(np.asarray(null["open"], dtype=np.float64))
    lc0 = np.log(np.asarray(null["close"], dtype=np.float64))
    lh0 = np.log(np.asarray(null["high"], dtype=np.float64))
    ll0 = np.log(np.asarray(null["low"], dtype=np.float64))
    top = lh0 - np.maximum(lo0, lc0)
    bot = np.minimum(lo0, lc0) - ll0
    lo = lo0 + (cum - add)
    lc = lc0 + cum
    out = dict(null)
    out["open"], out["close"] = np.exp(lo), np.exp(lc)
    out["high"] = np.exp(np.maximum(lo, lc) + top)
    out["low"] = np.exp(np.minimum(lo, lc) - bot)
    return out


def plant(
    null: Bars, cell: Cell | None, cfg: PlantedConfig, timeframe: str, seed: int
) -> tuple[Bars, Truth]:
    """``null`` with the edge of ``cell`` planted (``None``: the pure null)."""
    if cell is None:
        return dict(null), Truth(cell="null")
    kind, direction, strength = cell
    rng = np.random.default_rng(seed)
    n = np.asarray(null["close"]).size
    add = np.zeros(n)
    if kind == "MR":
        a = atr_fraction(null, cfg.mr.atr_length)
        p = cfg.mr.events_per_year / cfg.per_year(timeframe)
        k = cfg.mr.reversion_bars
        sign = -1.0 if direction == "long" else 1.0
        events: list[int] = []
        t = cfg.mr.atr_length + 1
        while t < n - k - 1:
            if rng.random() < p and np.isfinite(a[t]):
                move = strength * a[t]
                add[t] += sign * move
                add[t + 1 : t + 1 + k] -= sign * move / k
                events.append(t)
                t += k + 1
            else:
                t += 1
        return _rebuild(null, add), Truth(cell=cell_key(cell), events=tuple(events))
    if kind == "TF":
        lc = np.log(np.asarray(null["close"], dtype=np.float64))
        vol = float(np.diff(lc).std()) if n > 2 else 0.0
        p = cfg.tf.segments_per_year / cfg.per_year(timeframe)
        seg = cfg.tf.length(timeframe)
        sgn = 1 if rng.random() < 0.5 else -1
        segments: list[tuple[int, int, int]] = []
        t = 1
        while t < n - seg:
            if rng.random() < p:
                add[t : t + seg] += sgn * strength * vol
                segments.append((t, t + seg, sgn))
                sgn = -sgn
                t += seg
            else:
                t += 1
        return _rebuild(null, add), Truth(cell=cell_key(cell), segments=tuple(segments))
    raise ValueError(f"unknown planted edge type {kind!r}")


def own_statistic(bars: Bars, truth: Truth, cfg: PlantedConfig) -> float:
    """The planted effect in its own units (T15a plan §4): MR -- the mean forward return over
    the reversion window after an event, in ATR units and in the edge's direction, minus the
    same after every other bar; TF -- the mean signed return inside the segments, in units of
    the bar volatility. NaN when nothing was planted."""
    lc = np.log(np.asarray(bars["close"], dtype=np.float64))
    if truth.events:
        k = cfg.mr.reversion_bars
        a = atr_fraction(bars, cfg.mr.atr_length)
        fwd = np.full(lc.size, np.nan)
        fwd[:-k] = (lc[k:] - lc[:-k]) / np.where(a[:-k] > 0, a[:-k], np.nan)
        sign = 1.0 if truth.cell.split("|")[1] == "long" else -1.0
        marks = np.zeros(lc.size, dtype=bool)
        marks[list(truth.events)] = True
        ok = np.isfinite(fwd)
        return float(sign * (np.nanmean(fwd[ok & marks]) - np.nanmean(fwd[ok & ~marks])))
    if truth.segments:
        r = np.diff(lc, prepend=lc[0])
        sd = float(r[1:].std())
        signed = [s * r[a:b] for a, b, s in truth.segments]
        return float(np.concatenate(signed).mean() / sd) if sd > 0 else float("nan")
    return float("nan")
