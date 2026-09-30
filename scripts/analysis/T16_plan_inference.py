"""T16 plan, §7 (2)-(4): the HAC lag rule, the bootstrap block length, the CSCV partition count and
Hansen's SPA through ``arch``, measured on cases with a known answer. Measurement only::

    uv run python scripts/analysis/T16_plan_inference.py hac      # -> docs/reviews/T16_plan_hac.csv
    uv run python scripts/analysis/T16_plan_inference.py boot     # -> docs/reviews/T16_plan_boot.csv
    uv run python scripts/analysis/T16_plan_inference.py cscv     # -> docs/reviews/T16_plan_cscv.csv
    uv run python scripts/analysis/T16_plan_inference.py spa      # -> docs/reviews/T16_plan_spa.csv

* **hac** -- size of the two-sided 5 % t-test of "mean return = 0" on series whose mean **is** 0,
  daily AR(1) with phi in {0, 0.1, 0.3} and a GARCH(1,1) case, T in {250, 1000, 2500}, under each lag
  rule: none (the plain t-test), Newey-West (1994) ``floor(4 (T/100)^(2/9))``, ``floor(T^(1/4))``,
  and Andrews (1991)'s AR(1) plug-in for the Bartlett kernel. Nominal: 5 %.
* **boot** -- coverage of the 95 % percentile interval for the Sharpe ratio and the mean, whose true
  values are known, under the stationary bootstrap with block length 1 (i.i.d.), ``T^(1/3)``, and
  Politis-White (2004, with Patton et al. 2009's correction; ``arch.bootstrap.optimal_block_length``).
  Nominal: 95 %.
* **cscv** -- PBO (Bailey et al. 2017) for S in {8, 10, 12, 16} partitions and N in {50, 200, 1000,
  5000} trials: on pure-noise trials (the known answer is 0.5) and with one planted trial with a
  moderate (daily Sharpe 0.1) or strong (0.3) edge (the answer is near 0 for a strong one); its
  spread across seeds and its runtime.
* **spa** -- ``arch``'s SPA on the null (every model's mean return 0; nominal rejection 5 %) and with
  one planted superior model, for 10 / 100 / 1000 models; its runtime.
"""

from __future__ import annotations

import sys
import time
from itertools import combinations
from math import comb
from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import norm

from strategy_factory.cli import utf8_output

REVIEWS = Path("docs") / "reviews"


# -- series with a known answer ---------------------------------------------------------------


def ar1(t: int, phi: float, rng: np.random.Generator, mu: float = 0.0) -> np.ndarray:
    e = rng.standard_normal(t + 200) * np.sqrt(1 - phi**2)  # unit unconditional variance
    x = np.empty_like(e)
    x[0] = e[0]
    for i in range(1, len(e)):
        x[i] = phi * x[i - 1] + e[i]
    return mu + x[200:]


def garch(t: int, rng: np.random.Generator, mu: float = 0.0) -> np.ndarray:
    """GARCH(1,1), omega 0.05, alpha 0.1, beta 0.85: unconditional variance 1."""
    omega, a, b = 0.05, 0.1, 0.85
    x = np.empty(t + 200)
    h = 1.0
    for i in range(len(x)):
        x[i] = np.sqrt(h) * rng.standard_normal()
        h = omega + a * x[i] ** 2 + b * h
    return mu + x[200:]


# -- HAC ----------------------------------------------------------------------------------------


def nw_t(x: np.ndarray, lags: int) -> float:
    """t-statistic of the mean with the Newey-West (Bartlett) long-run variance."""
    t = len(x)
    u = x - x.mean()
    s = u @ u / t
    for j in range(1, lags + 1):
        s += 2 * (1 - j / (lags + 1)) * (u[j:] @ u[:-j]) / t
    return float(x.mean() / np.sqrt(max(s, 1e-300) / t))


def lag_rule(rule: str, x: np.ndarray) -> int:
    t = len(x)
    if rule == "none":
        return 0
    if rule == "nw1994":
        return int(np.floor(4 * (t / 100) ** (2 / 9)))
    if rule == "t^1/4":
        return int(np.floor(t**0.25))
    # Andrews (1991), Bartlett kernel, AR(1) plug-in
    u = x - x.mean()
    rho = float(np.clip((u[1:] @ u[:-1]) / (u @ u), -0.97, 0.97))
    alpha1 = 4 * rho**2 / ((1 - rho) ** 2 * (1 + rho) ** 2)
    return int(np.floor(1.1447 * (alpha1 * t) ** (1 / 3)))


def run_hac(reps: int = 2000) -> pl.DataFrame:
    rows = []
    crit = norm.ppf(0.975)
    for process in ("ar1 phi=0", "ar1 phi=0.1", "ar1 phi=0.3", "garch"):
        for t in (250, 1000, 2500):
            rng = np.random.default_rng(t)
            rejections = {r: 0 for r in ("none", "nw1994", "t^1/4", "andrews")}
            lags_used = {r: [] for r in rejections}
            for _ in range(reps):
                x = (
                    garch(t, rng)
                    if process == "garch"
                    else ar1(t, float(process.split("=")[1]), rng)
                )
                for rule in rejections:
                    lags = lag_rule(rule, x)
                    lags_used[rule].append(lags)
                    rejections[rule] += abs(nw_t(x, lags)) > crit
            for rule, n in rejections.items():
                rows.append(
                    {"process": process, "T": t, "rule": rule, "size_pct": round(100 * n / reps, 2),
                     "median_lags": float(np.median(lags_used[rule])), "reps": reps}
                )  # fmt: skip
            print("hac", process, t, flush=True)
    return pl.DataFrame(rows)


# -- stationary bootstrap -----------------------------------------------------------------------


def sb_indices(t: int, block: float, reps: int, rng: np.random.Generator) -> np.ndarray:
    """Politis & Romano (1994) stationary-bootstrap indices, mean block length ``block``."""
    p = 1.0 / block
    idx = np.empty((reps, t), dtype=np.int64)
    idx[:, 0] = rng.integers(0, t, reps)
    new = rng.random((reps, t)) < p
    starts = rng.integers(0, t, (reps, t))
    for i in range(1, t):
        idx[:, i] = np.where(new[:, i], starts[:, i], (idx[:, i - 1] + 1) % t)
    return idx


def run_boot(series: int = 400, reps: int = 499) -> pl.DataFrame:
    from arch.bootstrap import optimal_block_length

    rows = []
    t = 1000
    mu = 0.05  # true mean; the unconditional sd is 1, so the true (daily) Sharpe is 0.05
    for process in ("ar1 phi=0", "ar1 phi=0.2", "garch"):
        rng = np.random.default_rng(7)
        hits = {m: [0, 0] for m in ("iid", "t^1/3", "politis_white")}
        blocks = {m: [] for m in hits}
        for _ in range(series):
            x = (
                garch(t, rng, mu)
                if process == "garch"
                else ar1(t, float(process.split("=")[1]), rng, mu)
            )
            pw = float(optimal_block_length(x)["stationary"].iloc[0])
            for method, block in (
                ("iid", 1.0),
                ("t^1/3", t ** (1 / 3)),
                ("politis_white", max(1.0, pw)),
            ):
                blocks[method].append(block)
                s = x[sb_indices(t, block, reps, rng)]
                means = s.mean(axis=1)
                sharpes = means / s.std(axis=1, ddof=1)
                lo_m, hi_m = np.percentile(means, [2.5, 97.5])
                lo_s, hi_s = np.percentile(sharpes, [2.5, 97.5])
                hits[method][0] += lo_m <= mu <= hi_m
                hits[method][1] += lo_s <= mu <= hi_s  # true Sharpe = mu / 1
        for method, (hm, hs) in hits.items():
            rows.append(
                {"process": process, "T": t, "method": method,
                 "coverage_mean_pct": round(100 * hm / series, 1),
                 "coverage_sharpe_pct": round(100 * hs / series, 1),
                 "median_block": round(float(np.median(blocks[method])), 2), "series": series}
            )  # fmt: skip
        print("boot", process, flush=True)
    return pl.DataFrame(rows)


# -- CSCV / PBO ---------------------------------------------------------------------------------


def pbo(returns: np.ndarray, s: int) -> tuple[float, int]:
    """PBO by CSCV (Bailey, Borwein, Lopez de Prado, Zhu 2017), Sharpe as the performance."""
    n, t = returns.shape
    blocks = np.array_split(np.arange(t), s)
    sums = np.stack([returns[:, b].sum(axis=1) for b in blocks], axis=1)
    sq = np.stack([(returns[:, b] ** 2).sum(axis=1) for b in blocks], axis=1)
    cnt = np.array([len(b) for b in blocks], dtype=float)
    logits = []
    for is_set in combinations(range(s), s // 2):
        m = np.zeros(s, dtype=bool)
        m[list(is_set)] = True

        def sharpe(mask: np.ndarray) -> np.ndarray:
            k = cnt[mask].sum()
            mean = sums[:, mask].sum(axis=1) / k
            var = sq[:, mask].sum(axis=1) / k - mean**2
            return mean / np.sqrt(np.maximum(var, 1e-300))

        best = int(np.argmax(sharpe(m)))
        oos = sharpe(~m)
        rank = (oos < oos[best]).sum() + 0.5 * ((oos == oos[best]).sum() - 1) + 1
        w = rank / (n + 1)
        logits.append(np.log(w / (1 - w)))
    lg = np.asarray(logits)
    return float((lg <= 0).mean()), len(lg)


def run_cscv(t: int = 2000) -> pl.DataFrame:
    rows = []
    for n in (50, 200, 1000, 5000):
        for s in (8, 10, 12, 16):
            if n == 5000 and s == 16:
                continue  # 12,870 splits x 5,000 trials: measured once below for the runtime
            for case in ("noise", "planted 0.1", "planted 0.3"):
                vals, secs = [], []
                for seed in range(5 if n <= 1000 else 2):
                    rng = np.random.default_rng(seed)
                    r = rng.standard_normal((n, t))
                    if case != "noise":  # one trial with a true daily Sharpe of 0.1 or 0.3
                        r[0] += float(case.split()[1])
                    t0 = time.perf_counter()
                    v, _ = pbo(r, s)
                    secs.append(time.perf_counter() - t0)
                    vals.append(v)
                rows.append(
                    {"n_trials": n, "S": s, "splits": comb(s, s // 2), "case": case,
                     "pbo_mean": round(float(np.mean(vals)), 3), "pbo_sd": round(float(np.std(vals)), 3),
                     "seeds": len(vals), "seconds": round(float(np.mean(secs)), 2),
                     "bars_per_block": t // s}
                )  # fmt: skip
                print("cscv", n, s, case, flush=True)
    rng = np.random.default_rng(0)
    t0 = time.perf_counter()
    v, _ = pbo(rng.standard_normal((5000, t)), 16)
    rows.append(
        {"n_trials": 5000, "S": 16, "splits": comb(16, 8), "case": "noise", "pbo_mean": round(v, 3),
         "pbo_sd": None, "seeds": 1, "seconds": round(time.perf_counter() - t0, 2), "bars_per_block": t // 16}
    )  # fmt: skip
    return pl.DataFrame(rows)


# -- SPA via arch -------------------------------------------------------------------------------


def run_spa(t: int = 1000) -> pl.DataFrame:
    from arch.bootstrap import SPA

    rows = []
    for n in (10, 100, 1000):
        for case in ("null", "planted"):
            sims = 200 if n == 10 else (50 if n == 100 else 10)
            rej, secs = 0, []
            for seed in range(sims):
                rng = np.random.default_rng(seed)
                returns = rng.standard_normal((t, n))
                if case == "planted":
                    returns[:, 0] += 0.1
                bench = np.zeros(t)  # "better than not trading"
                t0 = time.perf_counter()
                spa = SPA(-bench, -returns, block_size=10, reps=1000, seed=seed)  # losses
                spa.compute()
                secs.append(time.perf_counter() - t0)
                rej += float(spa.pvalues["consistent"]) < 0.05
            rows.append(
                {"n_models": n, "case": case, "rejection_pct": round(100 * rej / sims, 1),
                 "sims": sims, "seconds_per_call": round(float(np.mean(secs)), 3)}
            )  # fmt: skip
            print("spa", n, case, flush=True)
    return pl.DataFrame(rows)


def main() -> int:
    utf8_output()
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    runs = {"hac": run_hac, "boot": run_boot, "cscv": run_cscv, "spa": run_spa}
    for name, fn in runs.items():
        if what in (name, "all"):
            df = fn()
            df.write_csv(REVIEWS / f"T16_plan_{name}.csv")
            pl.Config.set_tbl_rows(100)
            pl.Config.set_tbl_cols(20)
            print(df)
    return 0


if __name__ == "__main__":
    sys.exit(main())
