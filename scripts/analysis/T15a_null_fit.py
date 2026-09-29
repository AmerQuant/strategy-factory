"""T15a plan, measurement M1: does a calibrated null match a real symbol's drift and volatility?

For a few real (symbol, timeframe) development segments, fit the null's parameters, generate
``--seeds`` null series per variant, and compare the statistics the stages depend on with the
real series: drift and volatility (D-654's requirement), the gap share of variance, the bar range
and ATR (every probe, stop and magnitude is in ATR units), tails and volatility clustering.

Variants (the plan's candidates). Every generated variant has **exact moments**: per slot, the
gap (previous close -> open) and the body (open -> close) are rescaled so their mean and standard
deviation equal the real ones, and the body carries the real gap-body correlation. High and low
come from a Brownian bridge over the body, scaled per slot so the mean wick matches the real one.

* ``gauss`` -- Gaussian innovations, constant volatility per slot.
* ``t`` -- Student-t innovations (unit variance, df from the real kurtosis), constant volatility.
* ``t_vp`` -- ``t`` times the real series' own **volatility path**: a causal EWMA of the real
  squared returns up to the previous bar (half-life ``--half-life`` bars), normalised to RMS 1
  per slot. Direction stays i.i.d.; only the scale follows the real regimes.
* ``control`` -- the D-615 reshuffled-returns control, for comparison (not a candidate).

A slot is a bar's position within its UTC trading date (1D: one slot; 1H: 7 regular slots, the
first carrying the overnight gap). Only development bars are read (``DataAccess``); nothing is
written outside ``--out``.

    uv run python scripts/analysis/T15a_null_fit.py --out <dir> [--seeds 200]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from strategy_factory.data.catalog import Catalog
from strategy_factory.data.config import load_split_config
from strategy_factory.data.split import DataAccess, RegistryLedger, SplitManager
from strategy_factory.data.store import SnapshotStore
from strategy_factory.registry.engine import make_engine
from strategy_factory.stages.control import permute_returns

CASES = [("SHW", "1D"), ("TXN", "1D"), ("AAPL", "1D"), ("EEM", "1D"), ("TSLA", "1H"), ("BAC", "1H")]
BARS_PER_YEAR = {"1D": 252.0, "1H": 252.0 * 7}
ATR_N = 14
VARIANTS = ("gauss", "t", "t_vp")


def data_access() -> DataAccess:
    store = SnapshotStore()
    catalog = Catalog(store.root)
    return DataAccess(SplitManager(RegistryLedger(make_engine()), load_split_config(), store, catalog))


def slots(ts_us: np.ndarray, timeframe: str) -> np.ndarray:
    """Position of each bar within its UTC trading date (0 = the date's first bar), capped at 6."""
    out = np.zeros(ts_us.size, dtype=np.int64)
    if timeframe == "1D":
        return out
    day = ts_us // 86_400_000_000
    for i in range(1, ts_us.size):
        out[i] = out[i - 1] + 1 if day[i] == day[i - 1] else 0
    return np.minimum(out, 6)


def fit(bars: dict[str, np.ndarray], slot: np.ndarray) -> dict[str, Any]:
    """Per-slot parameters from the real bars (bar 0 has no previous close and is skipped)."""
    lo, lh, ll, lc = (np.log(bars[c]) for c in ("open", "high", "low", "close"))
    gap = lo[1:] - lc[:-1]
    body = lc[1:] - lo[1:]
    wick = (lh[1:] - np.maximum(lo, lc)[1:]) + (np.minimum(lo, lc)[1:] - ll[1:])
    s = slot[1:]
    ret = lc[1:] - lc[:-1]
    k = float(((ret - ret.mean()) ** 4).mean() / ret.var() ** 2 - 3.0)
    params: dict[str, Any] = {"slots": {}, "excess_kurtosis": k, "close0": float(bars["close"][0])}
    for v in np.unique(s):
        m = s == v
        params["slots"][int(v)] = {
            "n": int(m.sum()),
            "gap_mu": float(gap[m].mean()),
            "gap_sd": float(gap[m].std()),
            "body_mu": float(body[m].mean()),
            "body_sd": float(body[m].std()),
            "rho": float(np.corrcoef(gap[m], body[m])[0, 1]) if gap[m].std() > 0 else 0.0,
            "wick_mean": float(wick[m].mean()),
        }
    return params


def vol_path(real: dict[str, np.ndarray], slot: np.ndarray, half_life: float) -> np.ndarray:
    """Causal EWMA volatility of the real close-to-close returns, known at the previous bar,
    in units of its slot's unconditional sd, normalised to RMS 1 per slot."""
    lc = np.log(real["close"])
    r = np.concatenate(([0.0], np.diff(lc)))
    z = np.zeros_like(r)
    for v in np.unique(slot):
        m = slot == v
        sd = r[m][1:].std() if m.sum() > 2 else 1.0
        z[m] = r[m] / (sd if sd > 0 else 1.0)
    lam = 0.5 ** (1.0 / half_life)
    var = np.empty_like(z)
    acc = 1.0
    for i in range(z.size):
        var[i] = acc  # returns up to i-1 only
        acc = lam * acc + (1.0 - lam) * z[i] ** 2
    out = np.sqrt(var)
    for v in np.unique(slot):
        k = slot == v
        out[k] /= np.sqrt(np.mean(out[k] ** 2))
    return out


def innovations(rng: np.random.Generator, n: int, kind: str, kurt: float) -> np.ndarray:
    if kind == "gauss":
        return rng.standard_normal(n)
    df = min(max(4.0 + 6.0 / max(kurt, 0.1), 4.5), 60.0)  # t excess kurtosis = 6 / (df - 4)
    return rng.standard_t(df, n) / np.sqrt(df / (df - 2.0))


def bridge_wicks(
    rng: np.random.Generator, body: np.ndarray, var: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Excursions of a Brownian bridge from 0 to ``body`` with variance ``var`` above
    max(0, body) and below min(0, body) (the exact max / min laws, drawn independently)."""
    u1 = rng.random(body.size)
    u2 = rng.random(body.size)
    mx = 0.5 * (body + np.sqrt(body**2 - 2.0 * var * np.log(u1)))
    mn = 0.5 * (body - np.sqrt(body**2 - 2.0 * var * np.log(u2)))
    return mx - np.maximum(body, 0.0), np.minimum(body, 0.0) - mn


def _exact(x: np.ndarray, mask: np.ndarray, mu: float, sd: float) -> None:
    """Rescale ``x[mask]`` in place to mean ``mu`` and standard deviation ``sd`` exactly."""
    v = x[mask]
    s = v.std()
    x[mask] = mu + (v - v.mean()) * (sd / s if s > 0 else 0.0)


def generate(
    real: dict[str, np.ndarray],
    slot: np.ndarray,
    params: dict[str, Any],
    seed: int,
    kind: str,
    wick_scale: dict[int, float] | None = None,
    vp: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = slot.size
    base = "t" if kind == "t_vp" else kind
    kurt = params["excess_kurtosis"]
    z1 = innovations(rng, n, base, kurt)
    z2 = innovations(rng, n, base, kurt)
    scale = vp if (kind == "t_vp" and vp is not None) else np.ones(n)
    gap = np.zeros(n)
    body = np.zeros(n)
    bvar = np.zeros(n)
    for v, p in params["slots"].items():
        m = slot == v
        m[0] = False
        rho = p["rho"]
        gap[m] = z1[m] * scale[m]
        body[m] = (rho * z1[m] + np.sqrt(1.0 - rho**2) * z2[m]) * scale[m]
        _exact(gap, m, p["gap_mu"], p["gap_sd"])
        _exact(body, m, p["body_mu"], p["body_sd"])
        bvar[m] = (p["body_sd"] * scale[m]) ** 2
    up, dn = bridge_wicks(rng, body, bvar)
    if wick_scale is not None:
        ws = np.array([wick_scale.get(int(v), 1.0) for v in slot])
        up, dn = up * ws, dn * ws
    lc = np.log(params["close0"]) + np.cumsum(gap + body)
    lo = lc - body
    out = dict(real)
    out["open"] = np.exp(lo)
    out["close"] = np.exp(lc)
    out["high"] = np.exp(np.maximum(lo, lc) + up)
    out["low"] = np.exp(np.minimum(lo, lc) - dn)
    return out


def wick_scales(
    real: dict[str, np.ndarray],
    slot: np.ndarray,
    params: dict[str, Any],
    kind: str,
    vp: np.ndarray | None = None,
) -> dict[int, float]:
    """Per-slot factor so the null's mean wick equals the real one (one calibration draw set)."""
    sums: dict[int, list[float]] = {}
    for seed in range(20):
        syn = generate(real, slot, params, 10_000 + seed, kind, None, vp)
        lo, lh, ll, lc = (np.log(syn[c]) for c in ("open", "high", "low", "close"))
        w = (lh - np.maximum(lo, lc)) + (np.minimum(lo, lc) - ll)
        for v in params["slots"]:
            sums.setdefault(v, []).append(float(w[1:][slot[1:] == v].mean()))
    return {v: params["slots"][v]["wick_mean"] / float(np.mean(sums[v])) for v in params["slots"]}


def atr_frac(b: dict[str, np.ndarray]) -> float:
    h, lo, c = b["high"], b["low"], b["close"]
    tr = np.maximum(h[1:] - lo[1:], np.maximum(abs(h[1:] - c[:-1]), abs(lo[1:] - c[:-1])))
    atr = np.convolve(tr, np.ones(ATR_N) / ATR_N, mode="valid")
    return float(np.median(atr / c[ATR_N:]))


def stats(b: dict[str, np.ndarray], tf: str, slot: np.ndarray) -> dict[str, float]:
    lo, lh, ll, lc = (np.log(b[c]) for c in ("open", "high", "low", "close"))
    r = np.diff(lc)
    gap = lo[1:] - lc[:-1]
    a = np.abs(r - r.mean())
    ypb = BARS_PER_YEAR[tf]
    out = {
        "drift_ann_pct": float(r.mean() * ypb * 100),
        "vol_ann_pct": float(r.std() * np.sqrt(ypb) * 100),
        "gap_var_share": float(gap.var() / r.var()),
        "range_bp": float(np.mean(lh - ll) * 1e4),
        "atr_pct": atr_frac(b) * 100,
        "excess_kurt": float(((r - r.mean()) ** 4).mean() / r.var() ** 2 - 3.0),
        "ac1_r": float(np.corrcoef(r[:-1], r[1:])[0, 1]),
        "ac1_abs_r": float(np.corrcoef(a[:-1], a[1:])[0, 1]),
        "ohlc_consistent": float(
            np.all(b["high"] >= np.maximum(b["open"], b["close"]) * (1 - 1e-12))
            and np.all(b["low"] <= np.minimum(b["open"], b["close"]) * (1 + 1e-12))
        ),
    }
    if tf == "1H":
        s = slot[1:]
        out["vol_slot0_bp"] = float(r[s == 0].std() * 1e4)
        out["vol_slot1_6_bp"] = float(r[s > 0].std() * 1e4)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--half-life", type=float, default=20.0, help="EWMA half-life, 1D bars")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    da = data_access()
    rows: list[dict[str, Any]] = []
    fits: dict[str, Any] = {}
    for sym, tf in CASES:
        real = da.arrays(sym, tf)
        slot = slots(real["ts"], tf)
        params = fit(real, slot)
        vp = vol_path(real, slot, args.half_life * (7 if tf == "1H" else 1))
        fits[f"{sym}|{tf}"] = params
        rows.append({"symbol": sym, "tf": tf, "variant": "real", "stat": "value",
                     **stats(real, tf, slot)})  # fmt: skip
        scales: dict[str, Any] = {"control": None}
        for kind in VARIANTS:
            scales[kind] = wick_scales(real, slot, params, kind, vp)
            params[f"wick_scale_{kind}"] = scales[kind]
        for name, ws in scales.items():
            per: list[dict[str, float]] = []
            for seed in range(args.seeds):
                if name == "control":
                    syn = permute_returns(real, seed)
                else:
                    syn = generate(real, slot, params, seed, name, ws, vp)
                per.append(stats(syn, tf, slot))
            df = pl.DataFrame(per)
            for stat, q in (("mean", None), ("p2.5", 2.5), ("p97.5", 97.5)):
                vals = {
                    c: float(np.mean(df[c].to_numpy()) if q is None else np.percentile(df[c].to_numpy(), q))
                    for c in df.columns
                }
                rows.append({"symbol": sym, "tf": tf, "variant": name, "stat": stat, **vals})
        print(sym, tf, "done", flush=True)
    pl.DataFrame(rows, infer_schema_length=None).write_csv(args.out / "T15a_null_fit.csv")
    (args.out / "T15a_null_fit_params.json").write_text(
        json.dumps(fits, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
