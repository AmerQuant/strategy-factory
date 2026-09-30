"""Render a funnel run's Persian HTML report (D-655, D-666, D-668; F-X.3, F-X.4).

One self-contained file, ``<artifacts>/funnels/<funnel_id>/report.html``:

* Plotly's bundle inlined **once**; each figure is a JSON island (``<script
  type="application/json">``) drawn by a small inline script -- no CDN, no MathJax, no topojson,
  ``displaylogo`` off;
* the font (Vazirmatn, OFL 1.1) inlined as a ``data:`` URI; all CSS inline;
* ``<html lang="fa" dir="rtl">``; every number, symbol, method, parameter and id goes through the
  ``ltr`` filter (``<bdi dir="ltr">``); digits are Latin (D-666);
* every number is read from the artifacts (:mod:`strategy_factory.reports.read`).

No external request of any kind: the report opens identically offline, years later.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup, escape

from strategy_factory.core.errors import ConfigError
from strategy_factory.reports import figures as F
from strategy_factory.reports.config import ReportConfig
from strategy_factory.reports.read import (
    S01,
    S02,
    S03,
    STAGES,
    FunnelContext,
    failing_criteria,
    planted_truth,
    quality_split,
)

#: Latin digits in their own left-to-right run (D-666: the user's decision)
STAGE_FA = {
    S01: Markup('مرحلهٔ <bdi dir="ltr">1</bdi> — کشف اج'),
    S02: Markup('مرحلهٔ <bdi dir="ltr">2</bdi> — غربال روش'),
    S03: Markup('مرحلهٔ <bdi dir="ltr">3</bdi> — بهینه‌سازی ورود'),
}
ARM_FA = {"real": "داده", "control": "کنترل"}


def ltr(value: Any) -> Markup:
    """A left-to-right run inside the right-to-left page (numbers, symbols, names, ids)."""
    return Markup('<bdi dir="ltr">') + escape(fmt(value)) + Markup("</bdi>")


def fmt(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, float):
        return f"{value:,.3f}" if abs(value) < 100 else f"{value:,.1f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def pct(value: Any) -> Markup:
    return ltr("—" if value is None else f"{100 * float(value):.2f} %")


class Figures:
    """Collects the figures of one report; each gets an id and a JSON island."""

    def __init__(self) -> None:
        self.items: list[tuple[str, dict[str, Any]]] = []

    def add(self, fig: dict[str, Any]) -> Markup:
        fid = f"fig-{len(self.items)}"
        self.items.append((fid, fig))
        payload = json.dumps(fig, allow_nan=False, default=_json_default).replace("</", "<\\/")
        return Markup(
            f'<div class="fig" id="{fid}"></div>'
            f'<script type="application/json" id="{fid}-data">{payload}</script>'
        )


def _json_default(value: Any) -> Any:
    raise TypeError(f"not JSON: {type(value).__name__}")


def _font(cfg: ReportConfig) -> str:
    if not cfg.font_file.is_file() or not cfg.font_licence.is_file():
        raise ConfigError(
            f"the report font or its licence is missing ({cfg.font_file}, {cfg.font_licence}): "
            "run scripts/fetch_vazirmatn.ps1 (D-666)"
        )
    return base64.b64encode(cfg.font_file.read_bytes()).decode("ascii")


def _plotly_js() -> str:
    from plotly.offline import get_plotlyjs

    return get_plotlyjs().replace("</script", "<\\/script")


def funnel_table(ctx: FunnelContext) -> list[dict[str, Any]]:
    rows = []
    for tf in ctx.timeframes:
        for stage in STAGES:
            real = ctx.run(tf, stage, "real")
            control = ctx.run(tf, stage, "control")
            rc = real.counts() if real else None
            cc = control.counts() if control else None
            rows.append({
                "timeframe": tf, "stage": stage, "real": rc, "control": cc,
                "real_status": real.status if real else None,
                "control_status": control.status if control else None,
            })  # fmt: skip
    return rows


def end_of_stage3(ctx: FunnelContext) -> list[dict[str, Any]]:
    """Per timeframe: the symbols that reach the end of stage 3 against the symbols in stage 1
    (D-656's share on a null run)."""
    out = []
    for tf in ctx.timeframes:
        r1, r3 = ctx.run(tf, S01, "real"), ctx.run(tf, S03, "real")
        scope = r1.counts()["symbols_entered"] if r1 else 0
        ended = r3.counts()["symbols_passed"] if r3 else 0
        out.append({"timeframe": tf, "scope": scope, "ended": ended,
                    "share": ended / scope if scope else None})  # fmt: skip
    return out


def render(ctx: FunnelContext, cfg: ReportConfig) -> str:
    env = Environment(
        loader=PackageLoader("strategy_factory.reports", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["ltr"] = ltr
    env.filters["pct"] = pct
    figs = Figures()
    heatmaps = {}
    for tf in ctx.timeframes:
        r1 = ctx.run(tf, S01, "real")
        if r1 and r1.entered():
            heatmaps[tf] = figs.add(F.universe_heatmap(r1, cfg.heatmap_max_symbols))
    stages = []
    for run in ctx.runs:
        stages.append({
            "run": run, "criteria": failing_criteria(ctx, run),
            "quality": quality_split(run) if run.stage == S01 else [],
        })  # fmt: skip
    shown = ctx.candidates[: cfg.max_candidate_sections]
    candidates = []
    for c in shown:
        s3 = c.stage3
        candidates.append({
            "c": c,
            "ess": figs.add(F.ess_breakdown(c.stage1)) if c.stage1 else None,
            "grid": figs.add(F.stage2_grid(c.stage2)) if c.stage2 else None,
            "h1": [figs.add(f) for f in F.stage3_surfaces(s3, "h1")],
            "h2": [figs.add(f) for f in F.stage3_surfaces(s3, "h2")],
            "spp": figs.add(F.spp_histogram(s3, cfg.spp_bins)),
        })  # fmt: skip
    truth = planted_truth(ctx)
    power = figs.add(F.planted_power(truth)) if truth else None
    html = env.get_template("funnel.html.j2").render(
        ctx=ctx,
        table=funnel_table(ctx),
        ended=end_of_stage3(ctx),
        stages=stages,
        heatmaps=heatmaps,
        candidates=candidates,
        rest=ctx.candidates[cfg.max_candidate_sections :],
        truth=truth,
        power=power,
        stage_fa=STAGE_FA,
        arm_fa=ARM_FA,
        font_b64=_font(cfg),
        plotly_js=Markup(_plotly_js()),
        figure_ids=[fid for fid, _ in figs.items],
    )
    return str(html)


def write_report(ctx: FunnelContext, cfg: ReportConfig) -> Path:
    path = ctx.artifacts / "funnels" / ctx.funnel_id / "report.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(ctx, cfg), encoding="utf-8", newline="\n")
    return path
