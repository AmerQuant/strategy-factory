"""D-660: the stage-7 statistics library is pure (T16). Arrays in, frozen results out: no registry,
no data layer, no config loading, no pipeline or stage, no file I/O, no global random state.

``stats/edge.py`` is stream A's stage-1 statistic (D-658) and is not part of this library."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

STATS = Path(__file__).resolve().parents[2] / "src" / "strategy_factory" / "stats"
LIBRARY = sorted(p for p in STATS.glob("*.py") if p.name not in {"edge.py", "__init__.py"})
FORBIDDEN_PREFIXES = (
    "strategy_factory.registry",
    "strategy_factory.data",
    "strategy_factory.core.config",
    "strategy_factory.pipeline",
    "strategy_factory.stages",
    "strategy_factory.engine",
    "polars",
    "pathlib",
    "io",
    "os",
    "shutil",
    "json",
    "yaml",
    "sqlalchemy",
    "psycopg",
    "random",
)
ALLOWED_INTERNAL = ("strategy_factory.stats.",)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_F_7_the_library_has_modules_to_check() -> None:
    assert {p.name for p in LIBRARY} >= {
        "results.py", "ttest.py", "bootstrap.py", "permutation.py", "neff.py", "dsr.py",
        "pbo.py", "spa.py",
    }  # fmt: skip


@pytest.mark.parametrize("path", LIBRARY, ids=lambda p: p.name)
def test_F_7_library_imports_no_io_registry_or_config(path: Path) -> None:
    bad = [
        name
        for name in _imports(path)
        if any(name == f or name.startswith(f + ".") for f in FORBIDDEN_PREFIXES)
        or (name.startswith("strategy_factory.") and not name.startswith(ALLOWED_INTERNAL))
    ]
    assert not bad, f"{path.name} imports {bad} (D-660)"


@pytest.mark.parametrize("path", LIBRARY, ids=lambda p: p.name)
def test_F_7_library_uses_no_global_random_state(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for pattern in ("np.random.seed", "np.random.rand", "np.random.normal", "default_rng()"):
        assert pattern not in text, f"{path.name}: {pattern} (randomness only through seed)"
