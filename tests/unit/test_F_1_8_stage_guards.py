"""Static guards on the stage modules (D-306, D-354, D-616; CLAUDE.md rules 1 and 2).

* no stage module imports ``SplitManager``, mentions ``open_holdout`` or reaches into
  ``DataAccess``'s private split manager -- a stage cannot open a holdout (D-616);
* ``RunContext`` has no split manager field;
* stage code takes the engine settings only from ``PipelineConfig.engine``: the literal
  ``DEFAULT_ENGINE_CONFIG`` never appears in it (D-354 (1));
* the literal ``"s06_robust"`` appears in no stage code but the stage-6 module (D-354 (2)).
  ``metrics/names.py`` also names it, as the producer of the stage-6 metrics, since T10b; the
  rule is about stage code, which is what these modules are.

The holdout check reads the **code** (imports, names, attributes), not the prose: a docstring
may explain why a stage has no split manager.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

from strategy_factory.stages.base import RunContext

SRC = Path(__file__).resolve().parents[2] / "src" / "strategy_factory"
STAGE_MODULES = sorted((SRC / "stages").glob("*.py")) + sorted((SRC / "baseline").glob("*.py"))


BANNED = {"SplitManager", "open_holdout", "open_holdout_with_conversion", "_splits"}


def code_names(source: str) -> set[str]:
    """Every identifier the code uses: imported names, names and attributes."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom | ast.Import):
            names.update(a.name.split(".")[-1] for a in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def test_F_1_8_d616_no_stage_module_can_reach_the_holdout() -> None:
    assert STAGE_MODULES, "no stage modules found"
    for path in STAGE_MODULES:
        used = code_names(path.read_text(encoding="utf-8")) & BANNED
        assert not used, f"{path.name} uses {sorted(used)}"


def test_F_1_8_d616_the_check_sees_code() -> None:
    assert code_names("from x import SplitManager") & BANNED
    assert code_names("ctx.data._splits.open_holdout('c', 's', '1D', stage='s')") & BANNED
    assert not code_names('"""a SplitManager is never here"""') & BANNED


def test_F_1_8_d616_run_context_has_no_split_manager() -> None:
    names = {f.name for f in dataclasses.fields(RunContext)}
    assert "split" not in names and "splits" not in names
    assert "data" in names  # DataAccess: the development segment only


def test_F_1_8_d354_stage_code_never_uses_the_default_engine_config() -> None:
    for path in STAGE_MODULES:
        assert "DEFAULT_ENGINE_CONFIG" not in path.read_text(encoding="utf-8"), path.name


def test_F_1_8_d354_the_stage6_id_is_written_only_where_allowed() -> None:
    stage6 = set((SRC / "stages").glob("*robust*.py"))
    for path in STAGE_MODULES:
        if path in stage6:
            continue
        assert '"s06_robust"' not in path.read_text(encoding="utf-8"), path
