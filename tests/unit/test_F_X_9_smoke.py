"""F-X.9: the package and every sub-package from design §3 import."""

from __future__ import annotations

import importlib

import pytest

import strategy_factory

SUBPACKAGES = [
    "core",
    "data",
    "data.adapters",
    "costs",
    "engine",
    "components",
    "components.indicators",
    "components.entries",
    "components.exits",
    "components.filters",
    "components.sizing",
    "metrics",
    "baseline",
    "diagnostics",
    "robustness",
    "stats",
    "registry",
    "gates",
    "stages",
    "pipeline",
    "reports",
    "evidence",
]


def test_F_X_9_package_imports_and_has_version() -> None:
    assert strategy_factory.__version__ == "0.1.0"


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_F_X_9_subpackage_imports_with_docstring(name: str) -> None:
    module = importlib.import_module(f"strategy_factory.{name}")
    assert module.__doc__, f"{name} needs a one-line docstring"
    assert len(module.__doc__.strip().splitlines()) == 1


def test_F_X_9_cli_module_imports() -> None:
    from strategy_factory.cli import app

    assert app.info.name == "sfac"
