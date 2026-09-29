"""The calibrated null (D-654, D-664): a random walk with the real series' drift and volatility.

Measured before it was built (T15a plan §2, ``scripts/analysis/T15a_null_fit.py``). For one
(symbol, timeframe) development segment:

* every bar has a **session slot** -- its position in its UTC trading date (1D: one slot; 1H: up
  to the configured cap, the first slot carrying the overnight gap);
* each bar is a **gap** (previous close -> open) and a **body** (open -> close), drawn per slot
  with the real gap-body correlation and then rescaled to the slot's real mean and standard
  deviation **exactly** -- so the realised drift and volatility are the real ones, and the series
  starts at the real first close and ends at the real last close;
* the innovations are unit-variance Student-t (df from the real kurtosis) or Gaussian, multiplied
  (``vol_path``) by the real series' own **causal** EWMA volatility path: a scale known at the
  previous bar, normalised to RMS 1 per slot. The direction of every bar is i.i.d.; only the scale
  follows the real regimes. It carries no edge;
* high and low come from a Brownian bridge over the body, scaled per slot so the mean wick equals
  the real one. OHLC is consistent in every bar.

The timestamps and every other column (volume, spread, ...) are the real ones: the calendar and
the cost inputs are the real symbol's (T15a §4). Nothing here reads beyond the bars it is given,
and it is never written to the store (D-654).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from strategy_factory.synthetic.config import NullConfig

Floats = npt.NDArray[np.float64]
Ints = npt.NDArray[np.int64]
Bars = dict[str, npt.NDArray[Any]]
DAY_US = 86_400_000_000


@dataclass(frozen=True)
class SlotFit:
    gap_mu: float
    gap_sd: float
    body_mu: float
    body_sd: float
    rho: float
    wick_mean: float


@dataclass(frozen=True)
class NullFit:
    slots: dict[int, SlotFit]
    excess_kurtosis: float
    close0: float


def session_slots(ts_us: npt.NDArray[np.int64], cap: int) -> Ints:
    """Each bar's position within its UTC trading date (0 = the date's first bar), capped."""
    out = np.zeros(ts_us.size, dtype=np.int64)
    if cap == 0 or ts_us.size == 0:
        return out
    day = np.asarray(ts_us, dtype=np.int64) // DAY_US
    for i in range(1, ts_us.size):
        out[i] = out[i - 1] + 1 if day[i] == day[i - 1] else 0
    return np.minimum(out, cap)


def _logs(bars: Bars) -> tuple[Floats, Floats, Floats, Floats]:
    return (
        np.log(np.asarray(bars["open"], dtype=np.float64)),
        np.log(np.asarray(bars["high"], dtype=np.float64)),
        np.log(np.asarray(bars["low"], dtype=np.float64)),
        np.log(np.asarray(bars["close"], dtype=np.float64)),
    )


def fit(bars: Bars, slot: Ints) -> NullFit:
    """Per-slot parameters of the real bars (bar 0 has no previous close and is skipped)."""
    lo, lh, ll, lc = _logs(bars)
    gap = lo[1:] - lc[:-1]
    body = lc[1:] - lo[1:]
    wick = (lh[1:] - np.maximum(lo, lc)[1:]) + (np.minimum(lo, lc)[1:] - ll[1:])
    ret = lc[1:] - lc[:-1]
    var = float(ret.var())
    kurt = float(((ret - ret.mean()) ** 4).mean() / var**2 - 3.0) if var > 0 else 0.0
    s = slot[1:]
    slots: dict[int, SlotFit] = {}
    for v in np.unique(s):
        m = s == v
        g, b = gap[m], body[m]
        rho = float(np.corrcoef(g, b)[0, 1]) if g.size > 2 and g.std() > 0 and b.std() > 0 else 0.0
        slots[int(v)] = SlotFit(
            gap_mu=float(g.mean()),
            gap_sd=float(g.std()),
            body_mu=float(b.mean()),
            body_sd=float(b.std()),
            rho=rho if np.isfinite(rho) else 0.0,
            wick_mean=float(wick[m].mean()),
        )
    return NullFit(slots=slots, excess_kurtosis=kurt, close0=float(bars["close"][0]))


def vol_path(bars: Bars, slot: Ints, half_life: float) -> Floats:
    """Causal EWMA volatility of the real close-to-close returns, known at the previous bar,
    in units of the slot's unconditional sd, normalised to RMS 1 per slot."""
    lc = np.log(np.asarray(bars["close"], dtype=np.float64))
    r = np.concatenate(([0.0], np.diff(lc)))
    z = np.zeros_like(r)
    for v in np.unique(slot):
        m = slot == v
        sd = float(r[m][1:].std()) if m.sum() > 2 else 1.0
        z[m] = r[m] / (sd if sd > 0 else 1.0)
    lam = 0.5 ** (1.0 / half_life)
    var = np.empty_like(z)
    acc = 1.0
    for i in range(z.size):
        var[i] = acc  # returns up to i - 1 only
        acc = lam * acc + (1.0 - lam) * z[i] ** 2
    out = np.sqrt(var)
    for v in np.unique(slot):
        k = slot == v
        rms = float(np.sqrt(np.mean(out[k] ** 2)))
        out[k] /= rms if rms > 0 else 1.0
    return out


def _innovations(rng: np.random.Generator, n: int, cfg: NullConfig, kurt: float) -> Floats:
    if cfg.innovations == "gaussian":
        return rng.standard_normal(n)
    df = min(max(4.0 + 6.0 / max(kurt, 0.1), cfg.df_min), cfg.df_max)
    out: Floats = rng.standard_t(df, n) / np.sqrt(df / (df - 2.0))
    return out


def _bridge_wicks(rng: np.random.Generator, body: Floats, var: Floats) -> tuple[Floats, Floats]:
    """Excursions of a Brownian bridge from 0 to ``body`` with variance ``var`` above
    max(0, body) and below min(0, body) (the exact max / min laws, drawn independently)."""
    u1 = 1.0 - rng.random(body.size)  # in (0, 1]: log is finite
    u2 = 1.0 - rng.random(body.size)
    mx = 0.5 * (body + np.sqrt(body**2 - 2.0 * var * np.log(u1)))
    mn = 0.5 * (body - np.sqrt(body**2 - 2.0 * var * np.log(u2)))
    return mx - np.maximum(body, 0.0), np.minimum(body, 0.0) - mn


def _exact(x: Floats, mask: npt.NDArray[np.bool_], mu: float, sd: float) -> None:
    """Rescale ``x[mask]`` in place to mean ``mu`` and standard deviation ``sd`` exactly."""
    v = x[mask]
    s = float(v.std())
    x[mask] = mu + (v - v.mean()) * (sd / s if s > 0 else 0.0)


def _draw(
    real: Bars,
    slot: Ints,
    nf: NullFit,
    cfg: NullConfig,
    scale: Floats,
    seed: int,
    wick_scale: dict[int, float] | None,
) -> Bars:
    rng = np.random.default_rng(seed)
    n = slot.size
    z1 = _innovations(rng, n, cfg, nf.excess_kurtosis)
    z2 = _innovations(rng, n, cfg, nf.excess_kurtosis)
    gap = np.zeros(n)
    body = np.zeros(n)
    bvar = np.zeros(n)
    for v, p in nf.slots.items():
        m = slot == v
        m[0] = False
        if not m.any():
            continue
        gap[m] = z1[m] * scale[m]
        body[m] = (p.rho * z1[m] + np.sqrt(1.0 - p.rho**2) * z2[m]) * scale[m]
        _exact(gap, m, p.gap_mu, p.gap_sd)
        _exact(body, m, p.body_mu, p.body_sd)
        bvar[m] = (p.body_sd * scale[m]) ** 2
    up, dn = _bridge_wicks(rng, body, bvar)
    if wick_scale is not None:
        ws = np.array([wick_scale.get(int(v), 1.0) for v in slot])
        up, dn = up * ws, dn * ws
    lc = np.log(nf.close0) + np.cumsum(gap + body)
    lo = lc - body
    out = dict(real)
    out["open"] = np.exp(lo)
    out["close"] = np.exp(lc)
    out["high"] = np.exp(np.maximum(lo, lc) + up)
    out["low"] = np.exp(np.minimum(lo, lc) - dn)
    return out


def _wick_scales(
    real: Bars, slot: Ints, nf: NullFit, cfg: NullConfig, scale: Floats, seed: int
) -> dict[int, float]:
    """Per-slot factor so the null's mean wick equals the real one."""
    sums: dict[int, list[float]] = {v: [] for v in nf.slots}
    for i in range(cfg.wick_calibration_draws):
        syn = _draw(real, slot, nf, cfg, scale, seed + 1 + i, None)
        lo, lh, ll, lc = _logs(syn)
        w = (lh - np.maximum(lo, lc)) + (np.minimum(lo, lc) - ll)
        for v in nf.slots:
            sel = w[1:][slot[1:] == v]
            if sel.size:
                sums[v].append(float(sel.mean()))
    out: dict[int, float] = {}
    for v, p in nf.slots.items():
        mean = float(np.mean(sums[v])) if sums[v] else 0.0
        out[v] = p.wick_mean / mean if mean > 0 else 1.0
    return out


def null_bars(real: Bars, timeframe: str, cfg: NullConfig, seed: int) -> Bars:
    """The calibrated null of ``real`` (development bars, ``ts`` in microseconds UTC)."""
    if np.asarray(real["close"]).size < 3:
        return dict(real)
    slot = session_slots(np.asarray(real["ts"], dtype=np.int64), cfg.cap(timeframe))
    nf = fit(real, slot)
    scale = (
        vol_path(real, slot, cfg.half_life(timeframe))
        if cfg.vol_path
        else np.ones(slot.size, dtype=np.float64)
    )
    seed_wicks = seed ^ 0x5F5E_0000  # the calibration draws never reuse the series' own stream
    wick_scale = _wick_scales(real, slot, nf, cfg, scale, seed_wicks)
    return _draw(real, slot, nf, cfg, scale, seed, wick_scale)
