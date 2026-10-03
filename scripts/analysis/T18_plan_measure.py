"""T18 plan, §3: light measurements on synthetic data (seconds each) behind the nine choices.
Measurement only; nothing here is the library; the store is only read (the catalog)::

    uv run python scripts/analysis/T18_plan_measure.py wfe          # §3 (1)
    uv run python scripts/analysis/T18_plan_measure.py windows      # §3 (2), D-150 on the store
    uv run python scripts/analysis/T18_plan_measure.py trade_boot   # §3 (3)
    uv run python scripts/analysis/T18_plan_measure.py consistency  # §3 (7)
    uv run python scripts/analysis/T18_plan_measure.py all

Outputs ``docs/reviews/T18_plan_<name>.csv``. Seeds are fixed (``np.random.default_rng`` with
literal seeds), so a re-run gives the same numbers.

* **wfe** -- a family of 50 parameter variants of one strategy (daily returns, sd 1 %, variants
  correlated at 0.8). Three worlds: every variant carries a true edge (an annual Sharpe of 1); no
  variant does (pure noise); one variant does. Rolling walk-forward, 4 y in-sample / 1 y
  out-of-sample over 8.5 y (D-150's 1D lengths on a typical development window); in each window
  the variant with the best in-sample Sharpe is selected (a stand-in for the plateau selection).
  Each WF efficiency definition, its gate result at 0.5, and how often an in-sample return <= 0
  occurs. 400 simulations per world.
* **windows** -- for every 1D / 1H reference in the store, the development window's length
  (span - holdout - embargo, from ``configs/data/split.yaml``) and the number of out-of-sample
  windows D-150's lengths give, and for two candidate 5 x 5 matrices the share of cells that fit at
  least 4 windows, at the median development length.
* **trade_boot** -- 300 trades whose P&L is AR(1) in trade order (phi 0, 0.3, 0.6) or comes in
  regimes (streaks). The true 95th percentile of the max drawdown, from fresh draws of the same
  process, against the bootstrap's estimate from one series: i.i.d. resampling and the stationary
  block bootstrap with Politis-White's length (T16's D-723 / D-725 conventions).
* **consistency** -- the equity curve's R^2 and K-ratio, and the coefficient of variation of yearly
  profit, for strategies with a constant true edge (annual Sharpe 0.5, 1, 2) over 2, 4, 8 years;
  and the KS test between the two halves' trade returns: its false-alarm rate with no change, and
  its power when the second half's mean halves.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import ks_2samp

from strategy_factory.cli import utf8_output

REVIEWS = Path("docs") / "reviews"
DAY = 252


# -- §3 (1): walk-forward efficiency -----------------------------------------------------------


def _family(world: str, n_var: int, t: int, rng: np.random.Generator) -> np.ndarray:
    """``t x n_var`` daily returns: sd 1 %, variants correlated at 0.8 via a common factor."""
    common = rng.standard_normal((t, 1))
    own = rng.standard_normal((t, n_var))
    x = 0.01 * (math.sqrt(0.8) * common + math.sqrt(0.2) * own)
    edge = 0.01 / math.sqrt(DAY)  # an annual Sharpe of 1 at sd 1 % a day
    if world == "edge everywhere":
        x += edge
    elif world == "edge in one variant":
        x[:, 0] += edge
    return x


def _ann_return(r: np.ndarray) -> float:
    return float(r.mean() * DAY)


def _sharpe(r: np.ndarray) -> float:
    sd = float(r.std(ddof=1))
    return float(r.mean() / sd * math.sqrt(DAY)) if sd > 0 else float("nan")


def run_wfe(sims: int = 400) -> pl.DataFrame:
    is_len, oos_len, total = 4 * DAY, DAY, int(8.5 * DAY)
    rows = []
    for world in ("edge everywhere", "edge in one variant", "pure noise"):
        rng = np.random.default_rng(18)
        stats: dict[str, list[float]] = {k: [] for k in (
            "ret_pooled", "ret_mean_of_ratios", "ret_skip_nonpos", "sharpe_pooled",
            "share_profitable_oos", "any_is_nonpos", "n_windows",
        )}  # fmt: skip
        for _ in range(sims):
            x = _family(world, 50, total, rng)
            is_r, oos_r, ratios, ratios_skip, is_s, oos_s = [], [], [], [], [], []
            start = 0
            while start + is_len + oos_len <= total:
                ins = x[start : start + is_len]
                oos = x[start + is_len : start + is_len + oos_len]
                best = int(np.argmax(ins.mean(axis=0) / ins.std(axis=0, ddof=1)))
                a_is, a_oos = _ann_return(ins[:, best]), _ann_return(oos[:, best])
                is_r.append(a_is)
                oos_r.append(a_oos)
                ratios.append(a_oos / a_is if a_is != 0 else float("nan"))
                if a_is > 0:
                    ratios_skip.append(a_oos / a_is)
                is_s.append(_sharpe(ins[:, best]))
                oos_s.append(_sharpe(oos[:, best]))
                start += oos_len
            m_is = float(np.mean(is_r))
            stats["ret_pooled"].append(float(np.mean(oos_r)) / m_is if m_is > 0 else float("nan"))
            stats["ret_mean_of_ratios"].append(float(np.nanmean(ratios)))
            stats["ret_skip_nonpos"].append(
                float(np.mean(ratios_skip)) if ratios_skip else float("nan")
            )
            m_is_s = float(np.mean(is_s))
            stats["sharpe_pooled"].append(
                float(np.mean(oos_s)) / m_is_s if m_is_s > 0 else float("nan")
            )
            stats["share_profitable_oos"].append(float(np.mean(np.array(oos_r) > 0)))
            stats["any_is_nonpos"].append(float(min(is_r) <= 0))
            stats["n_windows"].append(len(is_r))
        for name, vals in stats.items():
            v = np.array(vals, dtype=float)
            fin = v[np.isfinite(v)]
            rows.append({
                "world": world, "quantity": name, "sims": sims,
                "undefined_pct": round(100 * (1 - fin.size / v.size), 1),
                "median": round(float(np.median(fin)), 3) if fin.size else None,
                "p10": round(float(np.percentile(fin, 10)), 3) if fin.size else None,
                "p90": round(float(np.percentile(fin, 90)), 3) if fin.size else None,
                "gate_pass_pct": (
                    round(100 * float(np.mean(v >= (0.6 if name == "share_profitable_oos" else 0.5))), 1)
                    if name not in ("any_is_nonpos", "n_windows") else None
                ),
            })  # fmt: skip
        print("wfe", world, flush=True)
    return pl.DataFrame(rows)


# -- §3 (2): how many walk-forward windows the store's development windows fit ------------------


def run_windows() -> pl.DataFrame:
    from strategy_factory.data.catalog import Catalog
    from strategy_factory.data.config import load_split_config

    split = load_split_config()
    cat = Catalog().table().filter(pl.col("is_reference") & pl.col("timeframe").is_in(["1D", "1H"]))
    cat = cat.filter(pl.col("source").is_in(["alpaca", "dukascopy"]))
    span = (pl.col("last_ts") - pl.col("first_ts")).dt.total_days() / 365.25
    bars_per_year = pl.when(pl.col("timeframe") == "1D").then(252.0).otherwise(252.0 * 7)
    embargo = split.embargo_bars / bars_per_year
    holdout = pl.max_horizontal(
        pl.col("span_y") * split.holdout_fraction, pl.lit(split.holdout_min_months / 12)
    )
    df = cat.select("source", "symbol", "timeframe", span.alias("span_y")).with_columns(
        (pl.col("span_y") - holdout - embargo).alias("dev_y")
    )
    defaults = {"1D": (4.0, 1.0), "1H": (2.0, 0.5)}  # D-150
    df = df.with_columns(
        pl.struct("timeframe", "dev_y")
        .map_elements(
            lambda r: max(0, math.floor((r["dev_y"] - defaults[r["timeframe"]][0]) / defaults[r["timeframe"]][1])),
            return_dtype=pl.Int64,
        )
        .alias("oos_windows_d150")
    )  # fmt: skip
    rows = []
    for (source, tf), g in df.group_by("source", "timeframe", maintain_order=True):
        w = g["oos_windows_d150"]
        rows.append({
            "source": source, "timeframe": tf, "references": g.height,
            "dev_years_p10": round(float(g["dev_y"].quantile(0.1)), 2),
            "dev_years_median": round(float(g["dev_y"].median()), 2),
            "dev_years_p90": round(float(g["dev_y"].quantile(0.9)), 2),
            "windows_median": int(w.median()), "share_4_or_more": round(float((w >= 4).mean()), 3),
            "share_auto_shrink": round(float(((w < 4) & (w >= 1)).mean()), 3),
            "share_none": round(float((w < 1).mean()), 3),
        })  # fmt: skip
    out = pl.DataFrame(rows)
    # two candidate 5 x 5 matrices, at each group's median development length
    grids = {
        "1D A (D-150 centred)": ([2, 3, 4, 5, 6], [0.5, 0.75, 1.0, 1.25, 1.5]),
        "1D B (shorter)": ([1, 1.5, 2, 3, 4], [0.25, 0.5, 0.75, 1.0, 1.5]),
        "1H A (D-150 centred)": ([1, 1.5, 2, 2.5, 3], [0.25, 0.375, 0.5, 0.75, 1.0]),
        "1H B (shorter)": ([0.5, 1, 1.5, 2, 3], [0.125, 0.25, 0.5, 0.75, 1.0]),
    }
    cells = []
    for name, (iss, ooss) in grids.items():
        tf = name[:2]
        for (source, t), g in df.group_by("source", "timeframe", maintain_order=True):
            if t != tf:
                continue
            dev = float(g["dev_y"].median())
            fit = [math.floor((dev - a) / b) for a in iss for b in ooss]
            cells.append({
                "matrix": name, "source": source, "dev_years_median": round(dev, 2),
                "cells_4_or_more": sum(f >= 4 for f in fit), "cells_1_to_3": sum(1 <= f < 4 for f in fit),
                "cells_none": sum(f < 1 for f in fit),
            })  # fmt: skip
    pl.DataFrame(cells).write_csv(REVIEWS / "T18_plan_wf_matrix.csv")
    print(pl.DataFrame(cells))
    return out


# -- §3 (3): trade bootstrap, i.i.d. or blocks ---------------------------------------------------


def _trades(process: str, n: int, rng: np.random.Generator, size: int = 1) -> np.ndarray:
    """``size x n`` trade P&L, unit sd, mean 0.1 (a modest edge per trade)."""
    if process == "regimes":
        state = np.zeros((size, n), dtype=bool)
        s = rng.random(size) < 0.5
        for i in range(n):
            flip = rng.random(size) < 0.05  # regimes last 20 trades on average
            s = np.where(flip, ~s, s)
            state[:, i] = s
        return np.where(state, 0.6, -0.4) + rng.standard_normal((size, n)) * 0.9
    phi = float(process.split("=")[1])
    e = rng.standard_normal((size, n + 50)) * math.sqrt(1 - phi**2)
    x = np.empty_like(e)
    x[:, 0] = e[:, 0]
    for i in range(1, n + 50):
        x[:, i] = phi * x[:, i - 1] + e[:, i]
    return 0.1 + x[:, 50:]


def _max_dd(pnl: np.ndarray) -> np.ndarray:
    eq = np.cumsum(pnl, axis=-1)
    peak = np.maximum.accumulate(
        np.concatenate([np.zeros((*eq.shape[:-1], 1)), eq], axis=-1), axis=-1
    )[..., 1:]
    return (peak - eq).max(axis=-1)


def run_trade_boot(series: int = 200, reps: int = 1000, n: int = 300) -> pl.DataFrame:
    from arch.bootstrap import optimal_block_length

    rows = []
    for process in ("ar1 phi=0", "ar1 phi=0.3", "ar1 phi=0.6", "regimes"):
        rng = np.random.default_rng(31)
        true_p95 = float(np.percentile(_max_dd(_trades(process, n, rng, size=20000)), 95))
        est = {"iid": [], "block_pw": []}
        blocks = []
        for _ in range(series):
            x = _trades(process, n, rng)[0]
            est["iid"].append(float(np.percentile(_max_dd(x[rng.integers(0, n, (reps, n))]), 95)))
            b = max(1.0, float(optimal_block_length(x)["stationary"].iloc[0]))
            blocks.append(b)
            p = 1.0 / b
            idx = np.empty((reps, n), dtype=np.int64)
            idx[:, 0] = rng.integers(0, n, reps)
            new = rng.random((reps, n)) < p
            starts = rng.integers(0, n, (reps, n))
            for i in range(1, n):
                idx[:, i] = np.where(new[:, i], starts[:, i], (idx[:, i - 1] + 1) % n)
            est["block_pw"].append(float(np.percentile(_max_dd(x[idx]), 95)))
        for method, vals in est.items():
            v = np.array(vals)
            rows.append({
                "process": process, "method": method, "true_p95_max_dd": round(true_p95, 2),
                "est_median": round(float(np.median(v)), 2),
                "est_bias_pct": round(100 * (float(np.median(v)) / true_p95 - 1), 1),
                "share_underestimating": round(float(np.mean(v < true_p95)), 3),
                "median_block": round(float(np.median(blocks)), 2) if method == "block_pw" else 1.0,
                "series": series, "trades": n,
            })  # fmt: skip
        print("trade_boot", process, flush=True)
    return pl.DataFrame(rows)


# -- §3 (7): R^2, K-ratio, the coefficient of variation, the KS test -----------------------------


def _r2_kratio(eq: np.ndarray) -> tuple[float, float]:
    t = np.arange(len(eq), dtype=float)
    slope, icept = np.polyfit(t, eq, 1)
    fit = slope * t + icept
    ss_res = float(((eq - fit) ** 2).sum())
    ss_tot = float(((eq - eq.mean()) ** 2).sum())
    se = math.sqrt(ss_res / (len(eq) - 2)) / math.sqrt(float(((t - t.mean()) ** 2).sum()))
    return 1 - ss_res / ss_tot if ss_tot > 0 else float("nan"), slope / se / math.sqrt(len(eq))


def run_consistency(sims: int = 400) -> pl.DataFrame:
    rows = []
    rng = np.random.default_rng(47)
    for sharpe in (0.5, 1.0, 2.0):
        for years in (2, 4, 8):
            t = years * DAY
            r2s, ks, cvs = [], [], []
            for _ in range(sims):
                r = rng.standard_normal(t) * 0.01 + sharpe * 0.01 / math.sqrt(DAY)
                r2, kr = _r2_kratio(np.cumsum(r))
                r2s.append(r2)
                ks.append(kr)
                yearly = r.reshape(years, DAY).sum(axis=1)
                m = yearly.mean()
                cvs.append(float(yearly.std(ddof=1) / abs(m)) if m != 0 else float("nan"))
            r2a, cva = np.array(r2s), np.array(cvs)
            rows.append({
                "kind": "r2_kratio_cv", "annual_sharpe": sharpe, "years": years, "sims": sims,
                "r2_median": round(float(np.median(r2a)), 3),
                "share_r2_ge_0_8": round(float(np.mean(r2a >= 0.8)), 3),
                "kratio_median": round(float(np.median(ks)), 4),
                "cv_yearly_profit_median": round(float(np.nanmedian(cva)), 2),
                "cv_p90": round(float(np.nanpercentile(cva, 90)), 2),
            })  # fmt: skip
    for n in (50, 200, 500):
        false_alarm = power = 0
        for _ in range(sims):
            a, b = rng.standard_normal(n // 2) + 0.1, rng.standard_normal(n - n // 2) + 0.1
            false_alarm += ks_2samp(a, b).pvalue < 0.05
            c = rng.standard_normal(n - n // 2) + 0.05  # the edge halves in the second half
            power += ks_2samp(a, c).pvalue < 0.05
        rows.append({
            "kind": "ks_halves", "trades": n, "sims": sims,
            "false_alarm_pct": round(100 * false_alarm / sims, 1),
            "power_pct_edge_halves": round(100 * power / sims, 1),
        })  # fmt: skip
    print("consistency", flush=True)
    return pl.DataFrame(rows, infer_schema_length=None)


def main() -> int:
    utf8_output()
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    runs = {"wfe": run_wfe, "windows": run_windows, "trade_boot": run_trade_boot,
            "consistency": run_consistency}  # fmt: skip
    for name, fn in runs.items():
        if what in (name, "all"):
            df = fn()
            df.write_csv(REVIEWS / f"T18_plan_{name}.csv")
            pl.Config.set_tbl_rows(100)
            pl.Config.set_tbl_cols(20)
            pl.Config.set_tbl_formatting("ASCII_MARKDOWN")
            print(df)
    return 0


if __name__ == "__main__":
    sys.exit(main())
