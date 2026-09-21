"""Parity report (T11 §6, scaffolding): what a parity run reports, and how it is judged.

The comparison itself is §4 and arrives with the TradingView trade lists (**D-360**). What is
here now is everything that does not depend on them:

* :func:`reference_summary` -- the settings and the reference's own facts, so a report can be
  produced and reviewed before the trade lists exist;
* :class:`NetProfitDiff` -- the **two** net-profit figures of **D-364**: relative to
  ``abs(TV net profit)`` and relative to initial capital, with a **flag** when the first is
  unreliable because the TradingView net profit is small. The flag is reported, never decided.
* :func:`verdict` -- the D-011 judgement, given a matched share and a difference.

D-011: at least 98 % of trades matched and a net-profit difference of at most 3 %. The
thresholds come from the parity config, never from code (CLAUDE.md rule 1).
"""

from __future__ import annotations

from dataclasses import dataclass

from strategy_factory.core.parity_config import ParityConfig


@dataclass(frozen=True)
class NetProfitDiff:
    """The net-profit difference, reported both ways (D-364)."""

    engine: float
    tradingview: float
    initial_capital: float
    #: from ``ParityConfig.small_net_profit_share`` (D-364); a threshold, so never a literal
    small_share: float

    @property
    def absolute(self) -> float:
        return self.engine - self.tradingview

    @property
    def relative_to_tv(self) -> float | None:
        """``|difference| / |TV net profit|``; ``None`` when TradingView made exactly zero."""
        if self.tradingview == 0.0:
            return None
        return abs(self.absolute) / abs(self.tradingview)

    @property
    def relative_to_capital(self) -> float:
        """``|difference| / initial capital`` -- always defined, and stable near zero profit."""
        return abs(self.absolute) / self.initial_capital

    @property
    def tv_profit_is_small(self) -> bool:
        """The TradingView net profit is too small for the relative figure to mean much."""
        return abs(self.tradingview) < self.small_share * self.initial_capital

    def lines(self) -> list[str]:
        rel = self.relative_to_tv
        rel_text = "n/a (TradingView net profit is 0)" if rel is None else f"{rel:.4%}"
        out = [
            f"engine net profit     : {self.engine:,.2f}",
            f"TradingView net profit: {self.tradingview:,.2f}",
            f"difference            : {self.absolute:,.2f}",
            f"  relative to |TV|    : {rel_text}",
            f"  relative to capital : {self.relative_to_capital:.4%}",
        ]
        if self.tv_profit_is_small:
            out.append(
                "  FLAG: |TV net profit| is below "
                f"{self.small_share:.0%} of initial capital, so the relative-to-|TV| "
                "figure is unreliable -- reported, not decided (D-364)"
            )
        return out


@dataclass(frozen=True)
class Verdict:
    """The D-011 judgement of one reference."""

    matched_share: float
    diff: NetProfitDiff
    min_matched_share: float
    max_net_profit_diff: float

    @property
    def trades_ok(self) -> bool:
        return self.matched_share >= self.min_matched_share

    @property
    def profit_state(self) -> str:
        """``ok`` / ``failed`` on the relative-to-|TV| figure (D-011), or ``flagged``.

        D-364: when the TradingView net profit is small the relative figure is **flagged, not
        decided** -- the run reports it and the supervisor rules. So a flag is its own state:
        the run does *not* fall back to the capital figure and pass on it (it once did).
        """
        rel = self.diff.relative_to_tv
        if rel is None or self.diff.tv_profit_is_small:
            return "flagged"
        return "ok" if rel <= self.max_net_profit_diff else "failed"

    @property
    def profit_ok(self) -> bool:
        return self.profit_state == "ok"

    @property
    def passed(self) -> bool:
        return self.trades_ok and self.profit_ok

    def lines(self) -> list[str]:
        mark = "PASS" if self.passed else "FAIL"
        return [
            f"D-011: {mark}",
            f"  matched trades: {self.matched_share:.2%} "
            f"(needs >= {self.min_matched_share:.0%}) -- {'ok' if self.trades_ok else 'FAILED'}",
            *[f"  {line}" for line in self.diff.lines()],
            f"  net profit within {self.max_net_profit_diff:.0%}: "
            + {
                "ok": "ok",
                "failed": "FAILED",
                "flagged": "FLAGGED -- not decided here; the supervisor rules (D-364)",
            }[self.profit_state],
        ]


def verdict(
    config: ParityConfig, matched_share: float, engine_net: float, tv_net: float
) -> Verdict:
    """The D-011 verdict, with both net-profit figures (D-364)."""
    return Verdict(
        matched_share=matched_share,
        diff=NetProfitDiff(
            engine_net, tv_net, config.pine.initial_capital, config.small_net_profit_share
        ),
        min_matched_share=config.min_matched_share,
        max_net_profit_diff=config.max_net_profit_diff,
    )


def reference_summary(config: ParityConfig, n_bars: int, first: str, last: str) -> list[str]:
    """The part of the report that does not need the trade lists (D-360)."""
    pine = config.pine
    return [
        f"reference : {config.reference.symbol} {config.reference.timeframe}"
        f" ({config.reference.chart_data})",
        f"bars      : {n_bars:,}  {first} .. {last}  (used as exported, D-348)",
        f"trade list: {config.reference.trade_list or 'NOT AVAILABLE YET (D-360)'}",
        f"pine      : atr_length {pine.atr_length}, capital {pine.initial_capital:,.0f}, "
        f"qty {pine.qty_type} {pine.qty_value:g}, commission {pine.commission_type} "
        f"{pine.commission_value:g}, slippage {pine.slippage_ticks} ticks "
        f"({pine.slippage_price():g}), pyramiding {pine.pyramiding}, "
        f"process_orders_on_close {pine.process_orders_on_close}, "
        f"calc_on_every_tick {pine.calc_on_every_tick}, bar_magnifier {pine.bar_magnifier}, "
        f"tz {pine.export_timezone}",
        f"engine    : parity_qty_step {config.engine.parity_qty_step:g}, "
        f"intrabar_mode {config.intrabar_mode}, costs from the pine block only (D-362)",
        f"strategy  : {config.strategy.entry if config.strategy else 'NOT MAPPED YET (D-361)'}",
        f"config    : {config.content_hash()[:16]}…",
    ]
