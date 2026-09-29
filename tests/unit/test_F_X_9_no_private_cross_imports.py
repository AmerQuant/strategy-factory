"""T15a plan §8 (T15b calibration item 9): the stage and component modules share helpers through
public names only. Stages 2 and 3 used stage 1's private ``_cost_arrays`` and
``_require_research_engine``; ``methods_tf`` used ``methods_mr``'s private parameter helpers.
Both now live in public homes (``stages/common.py``, ``components/entries/method_base.py``)."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCOPES = ("src/strategy_factory/stages", "src/strategy_factory/components")


def private_imports(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("strategy_factory"):
            for alias in node.names:
                if alias.name.startswith("_") and not alias.name.startswith("__"):
                    found.append(f"{node.module}.{alias.name}")
    return found


def test_F_X_9_stage_and_component_modules_import_no_private_name() -> None:
    offenders = {}
    for scope in SCOPES:
        for path in sorted((REPO / scope).rglob("*.py")):
            names = private_imports(path.read_text(encoding="utf-8"))
            if names:
                offenders[path.relative_to(REPO).as_posix()] = names
    assert offenders == {}


def test_F_X_9_the_private_import_check_fires() -> None:
    src = "from strategy_factory.stages.edge import UnsupportedSymbol, _cost_arrays\n"
    assert private_imports(src) == ["strategy_factory.stages.edge._cost_arrays"]
    assert private_imports("from strategy_factory.stages.common import cost_arrays\n") == []


def test_F_X_9_the_research_check_names_its_stage() -> None:
    """The message said "stage 1" in stages 2 and 3; it now names the calling stage."""
    source = (REPO / "src/strategy_factory/stages/common.py").read_text(encoding="utf-8")
    assert "stage 1 runs research" not in source
    for module in ("edge.py", "screen.py", "optimize.py"):
        text = (REPO / "src/strategy_factory/stages" / module).read_text(encoding="utf-8")
        assert "require_research_engine(ctx, STAGE)" in text, module
