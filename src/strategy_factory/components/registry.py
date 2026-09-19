"""Component registry (F-0.4.1): register by decorator, look up by name, list by role/edge.

Registration validates the component contract (name, role, parameter grid, entry tags and
the mirror rule). Stages only ever query the registry, so adding a method is one new
registered class.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, TypeVar

from strategy_factory.components.base import (
    DEFAULT_GRID_RULES,
    DIRECTIONS,
    NOT_MIRRORED_MARKER,
    ROLES,
    ComponentError,
    EntryComponent,
    GridRules,
    ParamSpec,
    Role,
    check_param_grid,
    has_not_mirrored_reason,
)
from strategy_factory.components.edges import EdgeTypes

T = TypeVar("T", bound=type[Any])

# Packages whose modules hold built-in components; every module in them is imported by
# :func:`default_registry`, so a new method file needs no change here.
COMPONENT_PACKAGES = (
    "strategy_factory.components.entries",
    "strategy_factory.components.exits",
    "strategy_factory.components.filters",
    "strategy_factory.components.sizing",
)


class ComponentRegistry:
    def __init__(self, grid_rules: GridRules = DEFAULT_GRID_RULES) -> None:
        self.grid_rules = grid_rules
        self._components: dict[str, type[Any]] = {}

    def register(self, cls: T) -> T:
        """Class decorator: validate ``cls`` and add it under ``cls.name``."""
        self._validate(cls)
        name: str = cls.name
        if name in self._components:
            raise ComponentError(f"component {name!r} is already registered")
        self._components[name] = cls
        return cls

    def _validate(self, cls: type[Any]) -> None:
        name = getattr(cls, "name", None)
        if not isinstance(name, str) or not name:
            raise ComponentError(f"{cls.__qualname__}: missing component name")
        role = getattr(cls, "role", None)
        if role not in ROLES:
            raise ComponentError(f"{name}: role must be one of {ROLES}, got {role!r}")
        params = getattr(cls, "params", None)
        if not isinstance(params, tuple) or not all(isinstance(p, ParamSpec) for p in params):
            raise ComponentError(f"{name}: params must be a tuple of ParamSpec")
        try:
            check_param_grid(params, self.grid_rules)
        except ComponentError as exc:
            raise ComponentError(f"{name}: {exc.message}") from exc
        if role == "entry":
            self._validate_entry(name, cls)

    @staticmethod
    def _validate_entry(name: str, cls: type[Any]) -> None:
        if not (isinstance(cls, type) and issubclass(cls, EntryComponent)):
            raise ComponentError(f"{name}: entry components must subclass EntryComponent")
        edge = getattr(cls, "edge_type", None)
        if not isinstance(edge, str) or not edge:
            raise ComponentError(f"{name}: entry components must declare edge_type")
        dirs = cls.directions
        if not dirs or len(set(dirs)) != len(dirs) or any(d not in DIRECTIONS for d in dirs):
            raise ComponentError(f"{name}: directions must be a non-empty subset of {DIRECTIONS}")
        if not cls.mirror:
            if not has_not_mirrored_reason(cls.__doc__):
                raise ComponentError(
                    f"{name}: mirror=False needs a written reason in the docstring "
                    f"({NOT_MIRRORED_MARKER!r} paragraph)"
                )
            own_short = any(
                "short_signals" in vars(k) for k in cls.__mro__ if k is not EntryComponent
            )
            if "short" in dirs and not own_short:
                raise ComponentError(f"{name}: mirror=False requires its own short_signals")

    def get(self, name: str) -> type[Any]:
        try:
            return self._components[name]
        except KeyError:
            raise ComponentError(f"unknown component {name!r}") from None

    def names(self) -> list[str]:
        return sorted(self._components)

    def list_by_role(self, role: Role) -> list[type[Any]]:
        if role not in ROLES:
            raise ComponentError(f"unknown role {role!r}")
        return [c for n, c in sorted(self._components.items()) if c.role == role]

    def entries(self) -> list[type[EntryComponent]]:
        return self.list_by_role("entry")

    def list_by_edge_type(self, edge_type: str, edges: EdgeTypes) -> list[type[EntryComponent]]:
        """Entry components tagged ``edge_type``; the type must exist in the edge registry."""
        edges.get(edge_type)
        return [c for c in self.entries() if c.edge_type == edge_type]

    def check_edge_tags(self, edges: EdgeTypes) -> None:
        """Every entry's ``edge_type`` (and probe ``group``) must exist in the edge registry."""
        for cls in self.entries():
            edge = edges.get(cls.edge_type)
            if cls.group is not None and cls.group not in edge.group_ids():
                raise ComponentError(
                    f"{cls.name}: group {cls.group!r} is not a group of edge type {edge.id} "
                    f"({list(edge.group_ids())})"
                )


REGISTRY = ComponentRegistry()
register = REGISTRY.register


def default_registry() -> ComponentRegistry:
    """The process-wide registry with every module of :data:`COMPONENT_PACKAGES` imported."""
    for package_name in COMPONENT_PACKAGES:
        package = importlib.import_module(package_name)
        for info in pkgutil.walk_packages(package.__path__, prefix=f"{package_name}."):
            importlib.import_module(info.name)
    return REGISTRY
