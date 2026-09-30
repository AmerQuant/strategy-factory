"""Plotly figures of the funnel report, as plain JSON dicts (D-655).

Every value is an artifact value; the figures only lay them out. A stage-3 surface is drawn **in
the artifact's axis order** (``grid.axes`` is an ordered list and ``surface`` is in C order over
it, T14): axis 0 is the heatmap's y, axis 1 its x, and ``z[i][j]`` is the cell ``i * n1 + j``. A
test compares a drawn surface cell by cell with its artifact, so the T14 transposition cannot come
back.
"""

from __future__ import annotations

from typing import Any

from strategy_factory.reports.read import S01, StageRun

FONT = "Vazirmatn, Tahoma, sans-serif"
Fig = dict[str, Any]


def _layout(title: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": {"text": title, "x": 0.5},
        "font": {"family": FONT, "size": 12},
        "margin": {"l": 60, "r": 20, "t": 50, "b": 50},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
    }
    base.update(extra)
    return base


PROFILES = (("MR", "long"), ("MR", "short"), ("TF", "long"), ("TF", "short"))


def universe_heatmap(run: StageRun, max_symbols: int) -> Fig:
    """Stage 1's ESS per symbol and profile (F-1.9, D-617): the universe heatmap."""
    ess: dict[str, dict[tuple[str, str], float | None]] = {}
    for r in run.entered():
        value = r.get("ess") or ""
        ess.setdefault(r["symbol"], {})[(r["edge_type"], r["direction"])] = (
            float(value) if value else None
        )
    best = sorted(ess, key=lambda s: -max((v or 0.0) for v in ess[s].values()))[:max_symbols]
    z = [[ess[s].get(p) for p in PROFILES] for s in best]
    return {
        "data": [
            {
                "type": "heatmap",
                "z": z,
                "x": [f"{e} {d}" for e, d in PROFILES],
                "y": best,
                "colorscale": "Viridis",
                "zmin": 0,
                "zmax": 100,
                "colorbar": {"title": {"text": "ESS"}},
                "hovertemplate": "%{y} %{x}: ESS %{z:.1f}<extra></extra>",
            }
        ],
        "layout": _layout(
            f"{run.timeframe} · ESS",
            height=max(300, 14 * len(best) + 120),
            yaxis={"autorange": "reversed", "automargin": True},
        ),
    }


def ess_breakdown(stage1: dict[str, Any]) -> Fig:
    points = stage1["profile"]["ess"].get("points", {})
    names = list(points)
    return {
        "data": [{"type": "bar", "x": names, "y": [points[n] for n in names]}],
        "layout": _layout("ESS", height=260, yaxis={"title": {"text": "points"}}),
    }


def stage2_grid(stage2: dict[str, Any]) -> Fig:
    """Stage 2's coarse grid, after costs (the cells as stored; D-623's cost leg)."""
    cells = stage2["grid"]
    names = list(cells[0]["params"]) if cells else []
    numeric = [n for n in names if all(isinstance(c["params"][n], int | float) for c in cells)]
    if len(names) == 2 and len(numeric) == 2:
        xs = sorted({c["params"][names[1]] for c in cells})
        ys = sorted({c["params"][names[0]] for c in cells})
        lookup = {(c["params"][names[0]], c["params"][names[1]]): c["target_cost"] for c in cells}
        z = [[lookup.get((y, x)) for x in xs] for y in ys]
        data: list[dict[str, Any]] = [
            {
                "type": "heatmap",
                "z": z,
                "x": xs,
                "y": ys,
                "colorscale": "RdBu",
                "zmid": 0,
                "colorbar": {"title": {"text": "target"}},
            }
        ]
        extra: dict[str, Any] = {
            "xaxis": {"title": {"text": names[1]}},
            "yaxis": {"title": {"text": names[0]}},
        }
    else:
        labels = [", ".join(f"{k}={v}" for k, v in c["params"].items()) for c in cells]
        data = [{"type": "bar", "x": labels, "y": [c["target_cost"] for c in cells]}]
        extra = {"xaxis": {"automargin": True}}
    return {"data": data, "layout": _layout("grid · after costs", height=320, **extra)}


def _index(axes: list[dict[str, Any]], values: dict[str, Any]) -> int:
    """C-order index of a cell over ``axes`` (the artifact's lattice order)."""
    idx = 0
    for a in axes:
        idx = idx * len(a["values"]) + a["values"].index(values[a["name"]])
    return idx


def surface_matrix(
    stage3: dict[str, Any], field: str
) -> tuple[list[Any], list[Any], list[list[Any]]]:
    """(y = axis-0 values, x = axis-1 values, z) of a two-axis surface, in the artifact's order."""
    axes = stage3["grid"]["axes"]
    n0, n1 = len(axes[0]["values"]), len(axes[1]["values"])
    cells = stage3["surface"]
    z = [[cells[i * n1 + j][field] for j in range(n1)] for i in range(n0)]
    return axes[0]["values"], axes[1]["values"], z


def stage3_surfaces(stage3: dict[str, Any], segment: str) -> list[Fig]:
    """Half ``segment`` ("h1" / "h2")'s smoothed after-cost surface, the plateau outlined and
    the selected cell marked; three axes as the slices through the selected cell."""
    field = f"smoothed_{segment}_cost"
    axes = stage3["grid"]["axes"]
    cells = stage3["surface"]
    sel = (stage3.get("selection") or {}).get("params") or {}
    title = {"h1": "half 1", "h2": "half 2"}[segment]
    if len(axes) == 1:
        a = axes[0]
        ys = [c[field] for c in cells]
        plateau = [c[field] if c["in_plateau"] else None for c in cells]
        data: list[dict[str, Any]] = [
            {
                "type": "scatter",
                "mode": "lines+markers",
                "x": a["values"],
                "y": ys,
                "name": "surface",
            },
            {
                "type": "scatter",
                "mode": "markers",
                "x": a["values"],
                "y": plateau,
                "name": "plateau",
                "marker": {"size": 11, "symbol": "square-open"},
            },
        ]
        if a["name"] in sel:
            j = a["values"].index(sel[a["name"]])
            data.append(
                {
                    "type": "scatter",
                    "mode": "markers",
                    "x": [a["values"][j]],
                    "y": [ys[j]],
                    "name": "selected",
                    "marker": {"size": 14, "symbol": "x"},
                }
            )
        return [{"data": data, "layout": _layout(f"{title} · {a['name']}", height=300)}]
    pairs = [(0, 1)] if len(axes) == 2 else [(0, 1), (0, 2), (1, 2)]
    out = []
    for p, q in pairs:
        ay, ax = axes[p], axes[q]
        fixed = {a["name"]: sel.get(a["name"]) for k, a in enumerate(axes) if k not in (p, q)}
        z: list[list[Any]] = []
        mask: list[list[int]] = []
        for yv in ay["values"]:
            row, mrow = [], []
            for xv in ax["values"]:
                values = {ay["name"]: yv, ax["name"]: xv, **fixed}
                c = cells[_index(axes, values)]
                row.append(c[field])
                mrow.append(1 if c["in_plateau"] else 0)
            z.append(row)
            mask.append(mrow)
        data = [
            {
                "type": "heatmap",
                "z": z,
                "x": ax["values"],
                "y": ay["values"],
                "colorscale": "RdBu",
                "zmid": 0,
                "colorbar": {"title": {"text": "target"}},
            },
            {
                "type": "contour",
                "z": mask,
                "x": ax["values"],
                "y": ay["values"],
                "showscale": False,
                "contours": {"start": 0.5, "end": 0.5, "size": 1, "coloring": "none"},
                "line": {"width": 2, "color": "black"},
                "hoverinfo": "skip",
                "name": "plateau",
            },
        ]
        if ay["name"] in sel and ax["name"] in sel:
            data.append(
                {
                    "type": "scatter",
                    "mode": "markers",
                    "x": [sel[ax["name"]]],
                    "y": [sel[ay["name"]]],
                    "name": "selected",
                    "marker": {"size": 14, "symbol": "x", "color": "black"},
                }
            )
        slice_note = ", ".join(f"{k}={v}" for k, v in fixed.items())
        out.append(
            {
                "data": data,
                "layout": _layout(
                    f"{title} · {ay['name']} x {ax['name']}"
                    + (f" ({slice_note})" if slice_note else ""),
                    height=380,
                showlegend=False,
                    xaxis={"title": {"text": ax["name"]}},
                    yaxis={"title": {"text": ay["name"]}},
                ),
            }
        )
    return out


def spp_histogram(stage3: dict[str, Any], bins: int) -> Fig:
    """F-3.5: the whole-window after-cost targets of every surface cell (failed cells excluded)."""
    values = [
        c["cost"]["target"][0] for c in stage3["surface"] if c["cost"]["target"][0] is not None
    ]
    spp = stage3["spp"]
    shapes = [
        {
            "type": "line",
            "x0": v,
            "x1": v,
            "yref": "paper",
            "y0": 0,
            "y1": 1,
            "line": {"dash": dash, "width": 2},
        }
        for v, dash in ((spp["median"], "solid"), (spp["p_low"], "dot"), (spp["p_high"], "dot"))
        if v is not None
    ]
    return {
        "data": [{"type": "histogram", "x": values, "nbinsx": bins}],
        "layout": _layout("SPP", height=280, shapes=shapes, bargap=0.05),
    }


def planted_power(rows: list[dict[str, Any]]) -> Fig:
    """Planted runs: the share of each cell's symbols with the planted profile at each stage."""
    stages = (S01, "s02_screen", "s03_entry")
    data = []
    for stage in stages:
        data.append(
            {
                "type": "bar",
                "name": stage,
                "x": [f"{r['timeframe']} {r['cell']}" for r in rows],
                "y": [r[stage] / r["symbols"] if r["symbols"] else None for r in rows],
            }
        )
    return {
        "data": data,
        "layout": _layout(
            "power", height=380, barmode="group", yaxis={"range": [0, 1], "tickformat": ".0%"}
        ),
    }
