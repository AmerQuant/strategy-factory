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

#: The references the gate runs. TF is two one-sided references (D-600): the engine runs one
#: direction per run, so the two-sided export is superseded and never read.
GATED = ("spy_mr_1d", "xauusd_tf_1h_long", "xauusd_tf_1h_short")


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

    Excluding it is only clean if **both** sides end the same way: flat on both, or open on
    both *with the same trade*. MR and TF short end flat; TF long ends open on both sides.
    """
    comparison, tv = run.comparison, run.tv
    assert all(p.tv_exit is not None for p in comparison.pairs if p.matched)
    assert len(comparison.pairs) == comparison.tv_trades
    assert set(comparison.excluded_open_tv) == set(tv.open_trades())
    tv_open = bool(tv.open_trades())
    assert comparison.excluded_open_engine == tv_open, "one side ends open, the other flat"
    if not tv_open:
        assert comparison.tv_trades == len(tv.trades())
        return
    # the same trade: TradingView's open entry is the engine's open entry
    from strategy_factory.selftest.parity_compare import tv_entry_bar

    (number,) = tv.open_trades()
    entry = next(r for r in tv.rows if r.trade == number and r.kind == "entry")
    held = run.result.equity.in_position
    start = len(held) - 1
    while start > 0 and held[start - 1]:
        start -= 1
    assert tv_entry_bar(run.chart, entry, run.daily) == start
    assert run.chart.open[start] == pytest.approx(entry.price, abs=run.config.pine.tick_size / 2)


def test_F_0_3_8_the_engine_open_flag_is_read_from_the_run() -> None:
    """Regression: the flag was read from ``result.meta`` behind a ``hasattr`` guard, but it
    lives on the run, so it was False for every reference. TF long ends open on both sides."""
    run = run_reference(config_of("xauusd_tf_1h_long"))
    assert run.result.open_position_marked
    assert run.comparison.excluded_open_engine
    assert run.comparison.excluded_open_tv == (520,)


def test_F_0_3_8_d011_a_missing_reference_fails_loudly(tmp_path: Path) -> None:
    """P-40 / D-360: a missing trade list is an error with a reason, never a skip or an xfail."""
    with pytest.raises((ConfigError, DataError, FileNotFoundError)) as excinfo:
        run_reference(config_of(GATED[0]), folder=tmp_path)
    assert "manifest" in str(excinfo.value).lower()
    # and a config whose Pine script is not mapped yet says exactly that
    unmapped = config_of(GATED[0]).model_copy(update={"strategy": None})
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


def test_F_0_3_8_d371_the_to_verify_ledger_does_not_drift() -> None:
    """D-371: after T11 exactly one parity choice is still `to_verify`, and it says so twice.

    The kernel docstring is what a reader of the engine sees and the T11 review is what a
    reader of the task sees. If they disagreed, one of them would send somebody looking for a
    TradingView export that cannot exist -- which is the thing D-371 exists to prevent.
    """
    from strategy_factory.engine import kernel

    def flat(text: str) -> str:
        return " ".join(text.split())

    doc = flat(kernel.__doc__ or "")
    review = (REPO / "docs" / "reviews" / "T11_review.md").read_text(encoding="utf-8")

    # still open: D-335 only, and it is waiting on the TF reference
    assert "Still **to_verify**: only the O->H->L->C path and its tie (D-335)" in doc
    assert "still `to_verify`" in review and "D-335" in review

    # both say, in as many words, that the other three are NOT to_verify, and why
    assert "no TradingView export can ever test these, so they are not to_verify" in doc
    assert "No TradingView export can ever close three of these five items" in review
    assert review.count("not `to_verify`") == 3  # one per closed item, in the table
    for item in ("D-327", "D-349 (a)", "D-349 (h)"):
        assert item in doc and item in review, item
    for text in ("confirmed by construction", "D-371"):
        assert text.lower() in doc.lower(), text
        assert text.lower() in review.lower(), text


def test_F_0_3_8_d335_the_intrabar_path_on_every_bar_that_touched_both_levels() -> None:
    """D-335 evidence, from the two TF references (the only ones with a stop AND a target).

    On a bar that touches both, ``tradingview`` mode goes O->H->L->C when the high is nearer the
    open, else O->L->H->C, and an exact tie takes the stop. The levels are recomputed here from
    the Pine rule -- ``math.round(k * ATR / mintick)`` ticks from the fill -- not taken from the
    engine, and every such bar must agree three ways: the path rule, the engine, TradingView.

    The counts are pinned because they are the evidence the T11 review quotes: over 919 trades
    exactly **one** bar touched both levels (target first), and there is **no** stop-first case
    and **no** exact tie. That is why D-335 is not closed by these references (P-46).
    """
    from decimal import ROUND_HALF_UP, Decimal

    def whole_ticks(distance: float, tick: float) -> float:
        n = Decimal(repr(distance / tick)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return float(n) * tick

    stop, target = 1, 2  # the engine's exit reasons
    seen = {"stop_first": 0, "target_first": 0, "tie": 0}
    for name, d in (("xauusd_tf_1h_long", 1), ("xauusd_tf_1h_short", -1)):
        run = run_reference(config_of(name))
        assert run.config.strategy is not None
        sl_k = run.config.strategy.exit["sl_atr"]
        tp_k = run.config.strategy.exit["tp_atr"]
        chart, t, tick = run.chart, run.result.trades, run.config.pine.tick_size
        tv_exit = {
            p.engine_index: run.tv.trades()[p.tv_index][1].signal
            for p in run.comparison.pairs
            if p.matched and p.engine_index is not None and p.tv_index is not None
        }
        for i in range(len(t.entry_idx)):
            reason = int(t.exit_reason[i])
            if reason not in (stop, target):
                continue
            j, fill, atr = int(t.exit_idx[i]), float(t.entry_price[i]), float(t.atr_at_entry[i])
            sl = fill - d * whole_ticks(sl_k * atr, tick)
            tp = fill + d * whole_ticks(tp_k * atr, tick)
            # the recomputed level is exactly the engine's fill, unless the open gapped past it
            level = sl if reason == stop else tp
            o, h, lo = chart.open[j], chart.high[j], chart.low[j]
            gapped = (o - level) * d * (1 if reason == target else -1) >= 0
            assert float(t.exit_price[i]) == (o if gapped else level), (name, i)
            if gapped:
                continue
            touched_sl = lo <= sl if d > 0 else h >= sl
            touched_tp = h >= tp if d > 0 else lo <= tp
            if not (touched_sl and touched_tp):
                continue
            up, down = h - o, o - lo
            if up == down:
                expected, key = stop, "tie"
            else:
                favour_first = (up < down) if d > 0 else (down < up)
                expected = target if favour_first else stop
                key = "target_first" if favour_first else "stop_first"
            seen[key] += 1
            assert reason == expected, (name, i, key)
            assert tv_exit[i] == ("TP" if expected == target else "SL"), (name, i, key)
    assert seen == {"stop_first": 0, "target_first": 1, "tie": 0}, seen


#: The reason table each reference produces -- the numbers the T11 review quotes. Pinned so a
#: change is deliberate: if P-48 is answered by sizing on the tick-rounded close, MR becomes
#: {"match": 462} and this line changes with the decision, not silently.
REASONS = {
    "spy_mr_1d": {"match": 457, "quantity": 5},
    "xauusd_tf_1h_long": {"match": 519},
    "xauusd_tf_1h_short": {"match": 400},
}


def test_F_0_3_8_d011_the_reason_table_is_the_reviewed_one(run: ParityRun) -> None:
    assert run.comparison.by_reason() == REASONS[run.config.name]
    assert set(REASONS) == set(GATED)
