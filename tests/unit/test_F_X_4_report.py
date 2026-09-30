"""F-X.3 / F-X.4 (T15a §5; D-655, D-666, D-668): the funnel's Persian HTML report.

A real funnel on the planted test series (stages 1 -> 2 -> 3, the stage tests' helpers) is read
and rendered; the tests check the report against the artifacts, never against the renderer's own
numbers: the first page's counts, a surface cell by cell in the artifact's axis order, no external
reference, the right-to-left / left-to-right marking, the font and its licence, and -- with a
headless Chromium behind a dead proxy -- that every figure draws with no network.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest
from fixtures.entry_stage import entry_config_file, entry_context, stage2_run
from fixtures.screen_stage import planted_series

from strategy_factory.reports import figures as F
from strategy_factory.reports.config import ReportConfig, load_report_config
from strategy_factory.reports.read import PASS_COLUMN, read_funnel
from strategy_factory.reports.render import render
from strategy_factory.stages.optimize import EntryStage

REPO = Path(__file__).resolve().parents[2]
FUNNEL = "00000000-0000-0000-0000-00000000f00d"
STAGES = ("s01_edge", "s02_screen", "s03_entry")


def report_config() -> ReportConfig:
    cfg = load_report_config(REPO / "configs" / "reports" / "funnel.yaml")
    return cfg.model_copy(
        update={"font_file": REPO / cfg.font_file, "font_licence": REPO / cfg.font_licence}
    )


@pytest.fixture(scope="module")
def funnel(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, dict[str, Any]]:
    root = tmp_path_factory.mktemp("funnel")
    symbols = ("AAPL", "MSFT")
    series = planted_series(symbols)
    stage2_run(root, series, symbols)
    ctx = entry_context(root, series, symbols)
    cfg = entry_config_file(root, fine_grid={"max_cells": 300})
    EntryStage(stage_config_path=cfg).run([(s, "1D") for s in symbols], ctx)
    folder = root / "funnels" / FUNNEL
    folder.mkdir(parents=True)
    summary = {
        "funnel_id": FUNNEL, "control": False, "resumed": False, "source": None, "seconds": 1.0,
        "stages": [{"timeframe": "1D", "stage": s, "arm": "real", "status": "done",
                    "run_id": "dry-run", "reused": False, "inputs": 2} for s in STAGES],
    }  # fmt: skip
    (folder / "funnel.json").write_text(json.dumps(summary), encoding="utf-8")
    row = {"source": "real", "control": False, "code_version": "c" * 40, "seed": 42}
    html = render(read_funnel(FUNNEL, root, row), report_config())
    return root, html, row


class Page(HTMLParser):
    """The parsed page: attributes, style text, and every body text node with its ancestors."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict[str, str | None]]] = []
        self.attrs: list[tuple[str, str, str]] = []  # (tag, name, value)
        self.texts: list[tuple[str, list[dict[str, str | None]]]] = []
        self.styles: list[str] = []
        self.slots: dict[str, str] = {}
        self.islands: dict[str, str] = {}
        self.root_dir: str | None = None
        self._island: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "html":
            self.root_dir = a.get("dir")
        for k, v in attrs:
            self.attrs.append((tag, k, v or ""))
            if k == "style" and v:
                self.styles.append(v)
        if tag == "script" and a.get("type") == "application/json":
            self._island = a.get("id")
        if tag not in ("meta", "link", "br", "img", "input"):
            self.stack.append((tag, a))

    def handle_endtag(self, tag: str) -> None:
        while self.stack:
            t, _ = self.stack.pop()
            if t == tag:
                break
        self._island = None

    def handle_data(self, data: str) -> None:
        tags = [t for t, _ in self.stack]
        if self._island:
            self.islands[self._island] = self.islands.get(self._island, "") + data
            return
        if "style" in tags:
            self.styles.append(data)
            return
        if "script" in tags or "head" in tags or not data.strip():
            return
        self.texts.append((data, [a for _, a in self.stack]))
        slot = next((a["data-slot"] for _, a in reversed(self.stack) if a.get("data-slot")), None)
        if slot is not None:
            self.slots[slot] = self.slots.get(slot, "") + data


def index(root: Path, stage: str) -> list[dict[str, str]]:
    with (root / "dry-run" / stage / "index.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def page(html: str) -> Page:
    p = Page()
    p.feed(html)
    return p


# -- D-655: every number on the first page equals its artifact value --------------------------
def test_F_X_4_d655_first_page_numbers_are_the_artifacts(funnel: Any) -> None:
    root, html, _ = funnel
    slots = page(html).slots
    assert slots, "the first page carries its numbers in data-slot cells"
    for stage in STAGES:
        rows = index(root, stage)
        if stage == "s01_edge":
            rows = [r for r in rows if r["status"] == "profiled"]
        passing = [r for r in rows if r[PASS_COLUMN[stage]] == "True"]
        assert int(slots[f"1D|{stage}|real|entered"]) == len(rows)
        assert int(slots[f"1D|{stage}|real|passed"]) == len(passing)
        assert int(slots[f"1D|{stage}|real|symbols_passed"]) == len({r["symbol"] for r in passing})
    scope = {r["symbol"] for r in index(root, "s01_edge") if r["status"] == "profiled"}
    ended = {r["symbol"] for r in index(root, "s03_entry") if r["gate_passed"] == "True"}
    assert int(slots["1D|end|scope"]) == len(scope)
    assert int(slots["1D|end|ended"]) == len(ended)


def test_F_X_4_every_stage3_entrant_has_a_section(funnel: Any) -> None:
    root, html, _ = funnel
    rows = index(root, "s03_entry")
    assert rows
    for r in rows:
        assert f'id="cand-1D-{r["symbol"]}-{r["direction"]}-{r["method"]}"' in html


# -- the surface in the artifact's axis order (the T14 transposition) ----------------------------
def _stage3(axes: list[tuple[str, list[float]]]) -> dict[str, Any]:
    """A hand-built stage-3 artifact whose cell values encode their own coordinates."""
    import itertools

    names = [n for n, _ in axes]
    cells = []
    for combo in itertools.product(*[v for _, v in axes]):  # C order over the ordered axes
        params = dict(zip(names, combo, strict=True))
        code = sum((k + 1) * 1000**i for i, k in enumerate(
            [axes[j][1].index(combo[j]) for j in range(len(axes))]))  # fmt: skip
        cells.append({"params": params, "smoothed_h1_cost": float(code), "smoothed_h2_cost": 0.0,
                      "in_plateau": False, "cost": {"target": [1.0, 1.0, 1.0]}})  # fmt: skip
    return {
        "grid": {"axes": [{"name": n, "values": v, "multiplier": 1} for n, v in axes]},
        "surface": cells,
        "selection": {"params": {n: v[1] for n, v in axes}},
        "spp": {"median": 1.0, "p_low": 0.5, "p_high": 1.5},
    }


def test_F_X_4_the_surface_is_drawn_in_the_artifacts_axis_order() -> None:
    art = _stage3([("n", [2, 3, 4]), ("t", [10.0, 20.0, 30.0, 40.0, 50.0])])  # non-square
    (fig,) = F.stage3_surfaces(art, "h1")
    heat = fig["data"][0]
    assert heat["y"] == [2, 3, 4] and heat["x"] == [10.0, 20.0, 30.0, 40.0, 50.0]
    for i in range(3):
        for j in range(5):
            assert heat["z"][i][j] == art["surface"][i * 5 + j]["smoothed_h1_cost"]
            assert heat["z"][i][j] == (i + 1) + (j + 1) * 1000


def test_F_X_4_three_axes_are_the_slices_through_the_selected_cell() -> None:
    art = _stage3([("a", [1, 2, 3]), ("b", [5, 6]), ("c", [7, 8, 9, 10])])
    figs = F.stage3_surfaces(art, "h1")
    assert len(figs) == 3
    ab = figs[0]["data"][0]  # a x b at c = its selected value (8, index 1)
    for i in range(3):
        for j in range(2):
            assert ab["z"][i][j] == (i + 1) + (j + 1) * 1000 + 2 * 1000**2


def test_F_X_4_the_real_surfaces_match_their_artifacts(funnel: Any) -> None:
    root, _, _ = funnel
    out = root / "dry-run" / "s03_entry"
    checked = 0
    for summary in sorted(out.glob("*/summary.json")):
        art = json.loads(summary.read_text(encoding="utf-8"))
        axes = art["grid"]["axes"]
        if len(axes) != 2:
            continue
        y, x, z = F.surface_matrix(art, "smoothed_h1_cost")
        (fig,) = F.stage3_surfaces(art, "h1")
        assert fig["data"][0]["z"] == z and fig["data"][0]["y"] == y and fig["data"][0]["x"] == x
        n1 = len(axes[1]["values"])
        for i, yv in enumerate(y):
            for j, xv in enumerate(x):
                cell = art["surface"][i * n1 + j]
                assert cell["params"][axes[0]["name"]] == yv
                assert cell["params"][axes[1]["name"]] == xv
        checked += 1
    assert checked >= 1


# -- D-655: self-contained, no external request ---------------------------------------------------
def test_F_X_4_d655_no_external_resource_reference(funnel: Any) -> None:
    _, html, _ = funnel
    p = page(html)
    for tag, name, value in p.attrs:
        if name in ("src", "href", "srcset", "action", "poster", "data"):
            assert value.startswith(("data:", "#")) or value == "", (tag, name, value[:80])
    for css in p.styles:
        for target in re.findall(r"url\(\s*['\"]?([^)'\"]*)", css):
            assert target.startswith("data:"), target[:80]
        assert "@import" not in css
    assert "<link" not in html
    assert html.count("Plotly.newPlot") == 1  # one inline bundle, one draw loop


def test_F_X_4_d666_rtl_page_with_every_latin_run_marked_ltr(funnel: Any) -> None:
    _, html, _ = funnel
    p = page(html)
    assert p.root_dir == "rtl"
    assert 'lang="fa"' in html
    bad = [
        text.strip()[:60]
        for text, ancestors in p.texts
        if re.search(r"[A-Za-z0-9]", text) and not any(a.get("dir") == "ltr" for a in ancestors)
    ]
    assert bad == []


def test_F_X_4_d666_the_rtl_check_catches_an_unmarked_number(funnel: Any) -> None:
    _, html, _ = funnel
    broken = html.replace("<h1>گزارش قیف</h1>", "<h1>گزارش قیف 2026</h1>", 1)
    p = page(broken)
    assert any("2026" in t and not any(a.get("dir") == "ltr" for a in anc) for t, anc in p.texts)


def test_F_X_3_d666_the_font_and_its_licence_are_in_the_repository(funnel: Any) -> None:
    _, html, _ = funnel
    cfg = report_config()
    assert cfg.font_licence.is_file()
    licence = cfg.font_licence.read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in licence.upper() and "Vazirmatn" in licence
    font = cfg.font_file.read_bytes()
    embedded = re.search(r"url\(data:font/ttf;base64,([A-Za-z0-9+/=]+)\)", html)
    assert embedded is not None
    assert (
        hashlib.sha256(base64.b64decode(embedded.group(1))).digest()
        == hashlib.sha256(font).digest()
    )


def test_F_X_3_a_missing_font_is_refused_with_the_fix(funnel: Any, tmp_path: Path) -> None:
    from strategy_factory.core.errors import ConfigError

    root, _, row = funnel
    cfg = report_config().model_copy(update={"font_file": tmp_path / "missing.ttf"})
    with pytest.raises(ConfigError, match="fetch_vazirmatn"):
        render(read_funnel(FUNNEL, root, row), cfg)


def test_F_X_4_d653_no_control_is_printed_on_the_first_page(funnel: Any) -> None:
    _, html, _ = funnel
    assert 'data-banner="no-control"' in html and 'data-banner="parity"' in html
    assert 'data-banner="synthetic"' not in html


# -- F-X.3: the report opens offline in a real browser --------------------------------------------
def _chromium() -> str | None:
    import os

    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        if found := shutil.which(name):
            return found
    for path in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ):
        if os.path.isfile(path):
            return path
    return None


@pytest.mark.browser
def test_F_X_3_d655_the_report_draws_every_figure_with_no_network(
    funnel: Any, tmp_path: Path
) -> None:
    browser = _chromium()
    if browser is None:
        pytest.skip("no headless Chromium found (CI fails on this skip, as for db)")
    _, html, _ = funnel
    target = tmp_path / "report.html"
    target.write_text(html, encoding="utf-8")
    figures = len(re.findall(r'<div class="fig" id="fig-\d+"></div>', html))
    proc = subprocess.run(
        [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-sandbox",
         "--disable-background-networking", "--disable-extensions",
         "--proxy-server=http://127.0.0.1:9", "--proxy-bypass-list=<-loopback>",
         f"--user-data-dir={tmp_path / 'profile'}", "--virtual-time-budget=20000",
         "--dump-dom", target.as_uri()],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )  # fmt: skip
    dom = proc.stdout
    assert figures > 0
    drawn = len(re.findall(r'class="main-svg"', dom))
    assert drawn >= figures, (drawn, figures, proc.stderr[-500:])


def test_F_X_3_ci_runs_the_browser_test_and_fails_on_a_skip() -> None:
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest -m browser -rs --junitxml=browser-junit.xml" in ci
    assert "Fail if the browser test was skipped" in ci


def test_F_X_4_d668_a_three_axis_candidate_without_a_selection_is_drawn() -> None:
    """D-647: a candidate with no valid cell has no selection (MRNA 1H `tf_ichimoku` in T14);
    its slices go through each other axis's middle value, labelled -- never a crash."""
    art = _stage3([("a", [1, 2, 3]), ("b", [5, 6]), ("c", [7, 8, 9, 10])])
    art["selection"] = {"params": None}
    figs = F.stage3_surfaces(art, "h1")
    assert len(figs) == 3
    assert "no selection" in figs[0]["layout"]["title"]["text"]
    ab = figs[0]["data"][0]  # c at its middle value, 9 (index 2)
    assert ab["z"][0][0] == 1 + 1000 + 3 * 1000**2
    assert all(d.get("name") != "selected" for d in figs[0]["data"])
