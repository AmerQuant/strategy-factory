"""The single registry of metric names (D-309, D-333, T10b).

Every metric a gate can reference is declared here once, with its unit, a one-line
description and the **producers** that emit it. The gate YAML is validated against this
registry when it loads (:func:`strategy_factory.gates.engine.load_gate_config`): an unknown
metric is an error, in the base stages and in every override.

Producers
---------
``metrics.core``
    The keys of :meth:`MetricsReport.as_gate_dict` (T09 plus the T08 run-meta counters and
    flags, D-345): one run, full metrics.
``metrics.batch``
    The keys of :func:`strategy_factory.metrics.batch.core_metrics_batch`: the grid path.
    These eight names are **also** produced by ``metrics.core`` and are bit-identical there,
    which is why :class:`MetricName` carries a tuple of producers rather than one.
``s01_probe``, ``s01_edge``, ``s01s_seasonal``, ``s02_screen`` … ``s07_stats``
    Stage-level metrics: the stage that computes them. They are registered now so the gate
    YAML validates before those stages exist (D-333).

A name is registered exactly once. Adding a field to ``MetricsReport`` without registering
it here fails ``tests/unit/test_F_0_8_1_metric_names.py``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

CORE = "metrics.core"
BATCH = "metrics.batch"

#: Units used below. They document the scale; nothing in code branches on them.
UNITS = frozenset(
    {
        "usd",
        "pct",  # percent of initial capital (D-005)
        "share",  # fraction in [0, 1]
        "ratio",
        "count",
        "flag",  # 0.0 / 1.0
        "years",
        "bars",
        "days",
        "percentile",  # 0..100
        "score",  # 0..100 composite score (ESS, F-1.6)
        "p_value",
        "index",
    }
)


@dataclass(frozen=True)
class MetricName:
    """One registered metric: its unit, what it means and who produces it."""

    name: str
    unit: str
    description: str
    producers: tuple[str, ...]

    @property
    def producer(self) -> str:
        """The first producer (the only one of every stage-level metric)."""
        return self.producers[0]


def _m(name: str, unit: str, description: str, *producers: str) -> MetricName:
    if unit not in UNITS:
        raise ValueError(f"metric {name!r}: unknown unit {unit!r}")
    if not producers:
        raise ValueError(f"metric {name!r}: needs at least one producer")
    return MetricName(name=name, unit=unit, description=description, producers=producers)


_ALL: tuple[MetricName, ...] = (
    # -- metrics.core, standard metrics (F-0.5.1) ----------------------------------------
    _m("years", "years", "Years covered; partial years count fractionally (D-006)", CORE),
    _m("total_net_profit_usd", "usd", "Net profit over the whole curve, after costs", CORE),
    _m("avg_annual_profit_usd", "usd", "Average annual net profit (D-006)", CORE, BATCH),
    _m("avg_annual_profit_pct", "pct", "Average annual net profit", CORE, BATCH),
    _m(
        "avg_annual_dd_ystart_usd",
        "usd",
        "Average annual drawdown from the start of each year (D-005 a); the gates use it",
        CORE,
        BATCH,
    ),
    _m(
        "avg_annual_dd_ystart_pct",
        "pct",
        "Average annual drawdown from the start of each year (D-005 a)",
        CORE,
        BATCH,
    ),
    _m(
        "avg_annual_dd_peak_usd",
        "usd",
        "Average annual drawdown against the all-time peak (D-005 b), reported only",
        CORE,
    ),
    _m(
        "avg_annual_dd_peak_pct",
        "pct",
        "Average annual drawdown against the all-time peak (D-005 b), reported only",
        CORE,
    ),
    _m(
        "profit_dd_ratio",
        "ratio",
        "Target metric: average annual profit / average annual drawdown (D-007)",
        CORE,
        BATCH,
    ),
    _m("exposure", "share", "Share of bars in a position", CORE, BATCH),
    _m("return_per_exposure", "ratio", "Average annual profit % divided by the exposure", CORE),
    _m("n_trades", "count", "Closed trades; the count the gates use (D-301)", CORE, BATCH),
    _m(
        "n_entries",
        "count",
        "Flat -> in-position transitions, diagnostic only (D-301)",
        CORE,
        BATCH,
    ),
    _m("profit_factor", "ratio", "Gross profit / gross loss, after costs", CORE),
    _m("win_rate", "share", "Share of closed trades with a positive net P&L", CORE),
    _m("avg_bars_held", "bars", "Average holding time in bars", CORE),
    _m("expectancy_usd", "usd", "Average net P&L per closed trade", CORE),
    _m("expectancy_pct", "pct", "Average net P&L per trade, % of the trade notional", CORE),
    _m("expectancy_atr", "ratio", "Average net P&L per trade in qty x ATR at entry", CORE),
    # -- metrics.core, risk and distribution metrics (F-0.5.2) ---------------------------
    _m("sharpe", "ratio", "Annualised Sharpe ratio of the daily returns", CORE),
    _m("sortino", "ratio", "Annualised Sortino ratio of the daily returns", CORE),
    _m("max_dd_pct", "pct", "Maximum drawdown over the whole curve", CORE),
    _m("ulcer_index", "index", "Ulcer index of the equity curve", CORE),
    _m("max_underwater_bars", "bars", "Longest underwater stretch in bars", CORE),
    _m("max_underwater_days", "days", "Longest underwater stretch in calendar days", CORE),
    _m("trade_return_skew", "ratio", "Skewness of the trade returns", CORE),
    _m("trade_return_excess_kurtosis", "ratio", "Excess kurtosis of the trade returns", CORE),
    # -- metrics.core, flags -------------------------------------------------------------
    _m("inf_ratio", "flag", "The target metric has a zero denominator (D-007)", CORE),
    _m("open_position_marked", "flag", "A position was still open at the last bar", CORE),
    _m("cost_placeholder", "flag", "The cost profile is a placeholder, not verified", CORE),
    # -- metrics.core, run meta from the engine (T08, D-345) -----------------------------
    _m(
        "n_skipped_min_volume",
        "count",
        "Entries skipped because the rounded quantity was below the minimum volume (D-313)",
        CORE,
    ),
    _m("min_volume_skip_flag", "flag", "n_skipped_min_volume > 0 (D-313)", CORE),
    _m(
        "volume_step_assumed",
        "flag",
        "The volume step was assumed, not from a profile (D-314)",
        CORE,
    ),
    _m("contracts_fixed", "flag", "Futures sized with the fixed contract count (D-329)", CORE),
    _m("fx_peg", "flag", "A fixed currency peg replaced a conversion pair (D-307)", CORE),
    # -- stage 1 -------------------------------------------------------------------------
    _m(
        "probe_percentile",
        "percentile",
        "Percentile of the probe in the random baseline",
        "s01_probe",
    ),
    _m("accepted_probe_groups", "count", "Accepted probe groups of one edge", "s01_edge"),
    _m(
        "probe_q_value",
        "p_value",
        "Benjamini-Hochberg q-value of the probe within its profile (D-605)",
        "s01_probe",
    ),
    _m("ess", "score", "Edge strength score, 0-100 (F-1.6, D-606, D-613)", "s01_edge"),
    # -- stage 1-S (seasonal, P1) --------------------------------------------------------
    _m("q_value", "p_value", "Benjamini-Hochberg adjusted p-value of the effect", "s01s_seasonal"),
    _m(
        "direction_stable_years_share",
        "share",
        "Share of years with the same effect direction",
        "s01s_seasonal",
    ),
    _m(
        "shift_1h_effect_retained",
        "share",
        "Share of the effect kept under a +-1 hour shift",
        "s01s_seasonal",
    ),
    _m("profit_cost_x1_5", "usd", "Net profit with cost stress 1.5", "s01s_seasonal"),
    # -- stage 2 -------------------------------------------------------------------------
    _m("grid_median_target", "ratio", "Median target metric of the coarse grid", "s02_screen"),
    _m(
        "profitable_cell_share", "share", "Share of grid cells profitable after costs", "s02_screen"
    ),
    _m(
        "overlap_with_selected", "share", "Trade overlap with the selected candidates", "s02_screen"
    ),
    _m(
        "min_trades_good_cells",
        "count",
        "Smallest closed-trade count of the good cells",
        "s02_screen",
    ),
    # -- stage 3 -------------------------------------------------------------------------
    _m("spp_median_target", "ratio", "Median target metric of the SPP distribution", "s03_entry"),
    _m("stability_ratio", "ratio", "Neighbourhood target metric / selected point", "s03_entry"),
    _m("plateau_area", "share", "Share of the search space inside the plateau", "s03_entry"),
    _m(
        "selected_in_both_halves",
        "flag",
        "The selected parameters are accepted in both data halves",
        "s03_entry",
    ),
    # -- stage 4 -------------------------------------------------------------------------
    _m("exit_improvement", "share", "Target-metric improvement over the base exit", "s04_exit"),
    _m(
        "exit_improvement_years_share",
        "share",
        "Share of years in which the exit improves the target metric",
        "s04_exit",
    ),
    _m("exit_spp_median_target", "ratio", "Median target metric of the exit SPP", "s04_exit"),
    _m("exit_stability_ratio", "ratio", "Neighbourhood / selected exit parameters", "s04_exit"),
    _m("exit_plateau_area", "share", "Plateau share of the exit search space", "s04_exit"),
    _m(
        "entry_still_in_plateau",
        "flag",
        "The entry parameters are still in their plateau",
        "s04_exit",
    ),
    _m("free_params_total", "count", "Free parameters of entry plus exit", "s04_exit"),
    # -- stage 5 -------------------------------------------------------------------------
    _m(
        "filter_improvement_percentile",
        "percentile",
        "Percentile of the filter improvement against 1000 random removals",
        "s05_filter",
    ),
    _m("trades_retained_share", "share", "Share of trades the filter keeps", "s05_filter"),
    _m("years_improved_share", "share", "Share of years the filter improves", "s05_filter"),
    _m(
        "bucket_min_trades",
        "count",
        "Smallest closed-trade count per calendar bucket",
        "s05_filter",
    ),
    _m("bucket_q_value", "p_value", "Benjamini-Hochberg adjusted p-value per bucket", "s05_filter"),
    _m(
        "bucket_direction_stable_years_share",
        "share",
        "Share of years with a stable bucket direction",
        "s05_filter",
    ),
    _m("bucket_stable_both_halves", "flag", "The bucket effect holds in both halves", "s05_filter"),
    _m("filter_count", "count", "Number of filters kept", "s05_filter"),
    # -- stage 6 -------------------------------------------------------------------------
    _m(
        "wf_efficiency",
        "ratio",
        "Walk-forward efficiency (out-of-sample / in-sample)",
        "s06_robust",
    ),
    _m(
        "wf_oos_profitable_share",
        "share",
        "Share of profitable walk-forward out-of-sample windows",
        "s06_robust",
    ),
    _m(
        "wf_matrix_success_share",
        "share",
        "Share of successful cells of the walk-forward matrix",
        "s06_robust",
    ),
    _m("profit_cost_x2", "usd", "Net profit with cost stress 2", "s06_robust"),
    _m(
        "mc_max_dd_p95_pct",
        "pct",
        "p95 of the Monte-Carlo maximum drawdown, % of initial capital (D-308)",
        "s06_robust",
    ),
    _m(
        "holdout_band_percentile",
        "percentile",
        "Percentile of the holdout result inside the expectation band",
        "s06_robust",
    ),
    # -- stage 7 -------------------------------------------------------------------------
    _m("t_test_p", "p_value", "p-value of the t-test on the trade returns (HAC)", "s07_stats"),
    _m("bootstrap_ci_lower", "ratio", "Lower bound of the bootstrapped CI", "s07_stats"),
    _m("permutation_p", "p_value", "p-value of the permutation test", "s07_stats"),
    _m("dsr", "ratio", "Deflated Sharpe ratio with the effective number of trials", "s07_stats"),
    _m("pbo", "share", "Probability of backtest overfitting (CSCV)", "s07_stats"),
    _m("spa_p", "p_value", "p-value of the Hansen SPA test", "s07_stats"),
    _m("min_trl_ratio", "ratio", "Minimum track record length / data length", "s07_stats"),
)


def _build() -> dict[str, MetricName]:
    out: dict[str, MetricName] = {}
    for m in _ALL:
        if m.name in out:
            raise ValueError(f"metric {m.name!r} is registered twice")
        out[m.name] = m
    return out


REGISTRY: dict[str, MetricName] = _build()


def registry() -> dict[str, MetricName]:
    """A copy of the registry; the module-level :data:`REGISTRY` is the single source."""
    return dict(REGISTRY)


def get(name: str) -> MetricName:
    """The registered metric ``name``; an unknown name raises :class:`KeyError`."""
    return REGISTRY[name]


def is_registered(name: str) -> bool:
    return name in REGISTRY


def names() -> frozenset[str]:
    return frozenset(REGISTRY)


def by_producer(producer: str) -> frozenset[str]:
    """Every metric name ``producer`` emits."""
    return frozenset(n for n, m in REGISTRY.items() if producer in m.producers)


def unknown(candidates: Iterable[str]) -> list[str]:
    """The unregistered names among ``candidates`` (sorted); ``[]`` means all are known."""
    return sorted(set(candidates) - names())
