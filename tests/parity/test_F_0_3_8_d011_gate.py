"""F-0.3.8 / D-011: the TradingView parity gate. Never skipped (CLAUDE.md rule 9).

It runs on the **committed reference fixtures** (D-359), so it runs in CI, where there is no
raw store. A reference joins the gate the moment its parity config gets a ``strategy`` block
(D-360: added with the trade list, never before -- no permanently failing test on ``main``),
and :func:`test_F_0_3_8_d011_every_mapped_reference_is_in_the_gate` makes that automatic
rather than a thing to remember.

The ATR is confirmed **before** any trade is compared (supervisor note 3): a mismatch there is
a separate finding, not a trade-matching reason. Here it is checked against an independent
Wilder RMA written from the definition, the way ``tests/oracle`` checks the engine -- the
comparison against TradingView's own exported ``ATR_14`` lives in
``tests/unit/test_F_0_4_2_golden.py``, which needs the raw store and therefore cannot gate CI.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.core.parity_config import ParityConfig, load_parity_config
from strategy_factory.selftest.parity_compare import atr_matches_tradingview, difference_table
from strategy_factory.selftest.parity_report import reference_summary
from strategy_factory.selftest.parity_run import ParityRun, run_reference

REPO = Path(__file__).resolve().parents[2]
CONFIGS = REPO / "configs" / "parity"

#: The references the gate runs today. TF is absent on purpose: its two-sided export is
#: superseded (D-600) and the one-sided exports have not arrived, so its config has no
#: ``strategy`` block yet.
GATED = ("spy_mr_1d",)


def config_of(name: str) -> ParityConfig:
    return load_parity_config(CONFIGS / f"{name}.yaml")


@pytest.fixture(scope="module", params=GATED)
def run(request: pytest.FixtureRequest) -> ParityRun:
    return run_reference(config_of(request.param))


def wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int) -> np.ndarray:
    """Wilder's ATR from the definition -- Pine's ``ta.atr``. Shares no code with the engine."""
    n = close.shape[0]
    out = np.full(n, np.nan)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    if n < length:
        return out
    out[length - 1] = tr[:length].mean()  # Pine seeds the RMA with the simple average
    for i in range(length, n):
        out[i] = (out[i - 1] * (length - 1) + tr[i]) / length
    return out


def test_F_0_3_8_d011_every_mapped_reference_is_in_the_gate() -> None:
    """A mapped reference that the gate does not run would be a silently untested one."""
    mapped = set()
    for path in sorted(CONFIGS.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw.get("strategy"):
            mapped.add(raw["name"])
    assert mapped == set(GATED), (
        f"parity configs with a strategy block: {sorted(mapped)}; gated: {sorted(GATED)}. "
        "A reference is mapped and gated together (D-360)."
    )


def test_F_0_3_8_d011_atr_is_wilders_before_any_trade_is_compared(run: ParityRun) -> None:
    """Supervisor note 3: confirm the ATR first; a mismatch here is its own finding."""
    chart, length = run.chart, run.config.pine.atr_length
    from strategy_factory.pipeline.backtest import market_arrays

    engine = market_arrays(chart.bars(), length).atr
    reference = wilder_atr(chart.high, chart.low, chart.close, length)
    agrees, worst, compared = atr_matches_tradingview(engine, reference, rtol=1e-12)
    assert compared > length, "nothing was compared"
    assert agrees, f"engine ATR differs from Wilder's RMA by {worst:.3e} over {compared} bars"


def test_F_0_3_8_d011_gate(run: ParityRun) -> None:
    """D-011: >= 98 % of trades matched and the net profit within 3 % (both from the config)."""
    comparison, verdict = run.comparison, run.verdict
    report = [
        *reference_summary(
            run.config,
            len(run.chart),
            *(when.date().isoformat() for when in run.chart.range()),
        ),
        f"trades: TradingView {comparison.tv_trades}, engine {comparison.engine_trades}",
        f"reasons: {comparison.by_reason()}",
        *verdict.lines(),
        *difference_table(comparison),
    ]
    assert verdict.passed, "\n".join(report)
    # the thresholds are the config's, never literals in the gate (CLAUDE.md rule 1)
    assert verdict.matched_share >= run.config.min_matched_share
    assert comparison.by_reason().get("match", 0) == comparison.matched


def test_F_0_3_8_d011_the_open_trade_is_excluded_on_both_sides(run: ParityRun) -> None:
    """Supervisor note 2: a position still open at the end of the export is not compared.

    The MR export ends flat, so this states that and checks that nothing was silently
    excluded; the exclusion itself is exercised on the TF export, which does end with an open
    trade, in ``tests/unit/test_F_0_3_8_parity_refs.py``.
    """
    assert all(p.tv_exit is not None for p in run.comparison.pairs if p.matched)
    assert len(run.comparison.pairs) == run.comparison.tv_trades
    assert set(run.comparison.excluded_open_tv) == set(run.tv.open_trades())
    if not run.tv.open_trades():
        assert not run.comparison.excluded_open_engine
        assert run.comparison.tv_trades == len(run.tv.trades())


def test_F_0_3_8_d011_a_missing_reference_fails_loudly(tmp_path: Path) -> None:
    """P-40 / D-360: a missing trade list is an error with a reason, never a skip or an xfail."""
    with pytest.raises((ConfigError, DataError, FileNotFoundError)) as excinfo:
        run_reference(config_of(GATED[0]), folder=tmp_path)
    assert "manifest" in str(excinfo.value).lower()
    # and a config whose Pine script is not mapped yet says exactly that
    unmapped = config_of("xauusd_tf_1h")
    assert unmapped.strategy is None
    with pytest.raises(ConfigError, match="no strategy block"):
        run_reference(unmapped)
    # ... and one whose export has not arrived says that, rather than skipping
    no_export = config_of(GATED[0]).model_copy(
        update={"reference": config_of(GATED[0]).reference.model_copy(update={"trade_list": None})}
    )
    with pytest.raises(ConfigError, match="never a skip"):
        run_reference(no_export)


def test_F_X_7_the_gate_run_is_reproducible(run: ParityRun) -> None:
    """D-365: re-running the same reference gives bit-identical trades and equity."""
    again = run_reference(run.config)
    first, second = run.result.trades, again.result.trades
    for field in ("entry_idx", "exit_idx", "qty", "entry_price", "exit_price", "pnl_net"):
        np.testing.assert_array_equal(getattr(first, field), getattr(second, field))
    np.testing.assert_array_equal(run.result.equity.equity_mtm, again.result.equity.equity_mtm)
