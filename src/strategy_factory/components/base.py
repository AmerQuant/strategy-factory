"""Strategy component interface (F-0.4.1) and edge/direction tags (F-0.4.3).

A component is a class with a ``name``, a ``role`` (``entry | exit | filter | sizing``) and a
list of :class:`ParamSpec`. Adding a method means writing one class and registering it with
:func:`strategy_factory.components.registry.register`; no stage code changes.

Entry components additionally declare an ``edge_type`` (validated against the config registry
``configs/edges/edge_types.yaml``) and the ``directions`` they may trade. **Mirror rule:** the
short entry is the long rule applied to the mirrored price series (see :meth:`Bars.mirrored`),
unless the class sets ``mirror = False`` and gives the reason in its docstring under a
``Not mirrored:`` paragraph (checked at registration).
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import ClassVar, Literal, Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, model_validator

from strategy_factory.core.errors import ConfigError

Role = Literal["entry", "exit", "filter", "sizing"]
Direction = Literal["long", "short"]
Trigger = Literal["state", "event"]
ParamKind = Literal["int", "float", "choice"]
ParamValue = int | float | str
FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

ROLES: tuple[Role, ...] = ("entry", "exit", "filter", "sizing")
DIRECTIONS: tuple[Direction, ...] = ("long", "short")
TRIGGERS: tuple[Trigger, ...] = ("state", "event")
NOT_MIRRORED_MARKER = "Not mirrored:"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ComponentError(ConfigError):
    """A component or its parameter declaration violates the component contract."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GridRules(_Frozen):
    """Coarse-grid rule: 2 to 4 values per parameter, <= 64 cells per method.

    D-110 fixed 4 values per parameter; **D-630** amends it to 2-4, because a choice or a small
    count has fewer than 4 meaningful values and a two-way choice is never padded to four.
    """

    min_coarse_values_per_param: int = Field(default=2, ge=1)
    max_coarse_values_per_param: int = Field(default=4, ge=1)
    max_coarse_cells: int = Field(default=64, ge=1)

    def values_ok(self, count: int) -> bool:
        return self.min_coarse_values_per_param <= count <= self.max_coarse_values_per_param

    def values_text(self) -> str:
        return f"{self.min_coarse_values_per_param} to {self.max_coarse_values_per_param}"


DEFAULT_GRID_RULES = GridRules()


def _is_integral(value: float) -> bool:
    return float(value).is_integer()


class ParamSpec(_Frozen):
    """Declaration of one component parameter.

    2 to 4 ``coarse_values`` (D-630). ``int``/``float`` parameters need
    ``min <= default <= max``, strictly increasing
    ``coarse_values`` inside ``[min, max]`` and a positive ``fine_step``. ``choice`` parameters
    list their options in ``coarse_values`` and have no ``min``/``max``/``fine_step``.
    """

    name: str
    kind: ParamKind
    default: ParamValue
    min: float | None = None
    max: float | None = None
    coarse_values: tuple[ParamValue, ...]
    fine_step: float | None = None

    @model_validator(mode="after")
    def _check(self) -> ParamSpec:
        if not _NAME_RE.match(self.name):
            raise ValueError(f"parameter name must be snake_case, got {self.name!r}")
        if not DEFAULT_GRID_RULES.values_ok(len(self.coarse_values)):
            raise ValueError(
                f"{self.name}: {DEFAULT_GRID_RULES.values_text()} coarse values required "
                f"(D-630), got {len(self.coarse_values)}"
            )
        if self.kind == "choice":
            self._check_choice()
        else:
            self._check_numeric()
        return self

    def _check_choice(self) -> None:
        if self.min is not None or self.max is not None or self.fine_step is not None:
            raise ValueError(f"{self.name}: choice parameters take no min/max/fine_step")
        if not all(isinstance(v, str) for v in self.coarse_values):
            raise ValueError(f"{self.name}: choice values must be strings")
        if len(set(self.coarse_values)) != len(self.coarse_values):
            raise ValueError(f"{self.name}: duplicate choice values")
        if self.default not in self.coarse_values:
            raise ValueError(f"{self.name}: default must be one of the choices")

    def _check_numeric(self) -> None:
        if self.min is None or self.max is None or self.fine_step is None:
            raise ValueError(f"{self.name}: numeric parameters need min, max and fine_step")
        values = (self.default, *self.coarse_values)
        if any(isinstance(v, str | bool) for v in values):
            raise ValueError(f"{self.name}: numeric parameter with non-numeric values")
        nums = [float(v) for v in values]
        if not all(math.isfinite(v) for v in (*nums, self.min, self.max, self.fine_step)):
            raise ValueError(f"{self.name}: values must be finite")
        if self.min > self.max:
            raise ValueError(f"{self.name}: min > max")
        if self.fine_step <= 0:
            raise ValueError(f"{self.name}: fine_step must be > 0")
        if any(not self.min <= v <= self.max for v in nums):
            raise ValueError(f"{self.name}: default and coarse values must lie in [min, max]")
        coarse = nums[1:]
        if any(b <= a for a, b in pairwise(coarse)):
            raise ValueError(f"{self.name}: coarse values must be strictly increasing")
        if self.kind == "int" and not all(
            _is_integral(v) for v in (*nums, self.min, self.max, self.fine_step)
        ):
            raise ValueError(f"{self.name}: int parameters need integral values")

    def coerce(self, value: ParamValue) -> ParamValue:
        """Validate one value for this parameter and return it in canonical type."""
        if self.kind == "choice":
            if value not in self.coarse_values:
                raise ComponentError(f"{self.name}: {value!r} is not one of {self.coarse_values}")
            return value
        if isinstance(value, str | bool):
            raise ComponentError(f"{self.name}: expected a number, got {value!r}")
        assert self.min is not None and self.max is not None
        if not self.min <= float(value) <= self.max:
            raise ComponentError(f"{self.name}: {value!r} outside [{self.min}, {self.max}]")
        if self.kind == "int":
            if not _is_integral(float(value)):
                raise ComponentError(f"{self.name}: expected an integer, got {value!r}")
            return int(value)
        return float(value)


def coarse_cells(params: Sequence[ParamSpec]) -> int:
    """Number of coarse-grid cells of a method (product of coarse-value counts)."""
    return math.prod(len(p.coarse_values) for p in params)


def check_param_grid(params: Sequence[ParamSpec], rules: GridRules = DEFAULT_GRID_RULES) -> None:
    """Raise :class:`ComponentError` if the declared grid breaks the coarse-grid rule."""
    names = [p.name for p in params]
    if len(set(names)) != len(names):
        raise ComponentError(f"duplicate parameter names: {names}")
    for p in params:
        if not rules.values_ok(len(p.coarse_values)):
            raise ComponentError(f"{p.name}: {rules.values_text()} coarse values required (D-630)")
    cells = coarse_cells(params)
    if cells > rules.max_coarse_cells:
        raise ComponentError(
            f"{cells} coarse-grid cells exceed the maximum of {rules.max_coarse_cells}"
        )


@dataclass(frozen=True)
class Bars:
    """OHLC arrays of one series (float64, same length) handed to components."""

    open: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray

    def __post_init__(self) -> None:
        n: int | None = None
        for field in ("open", "high", "low", "close"):
            arr = np.ascontiguousarray(getattr(self, field), dtype=np.float64)
            if arr.ndim != 1:
                raise ValueError(f"{field} must be 1-D")
            if n is not None and arr.shape[0] != n:
                raise ValueError("OHLC arrays must have the same length")
            n = arr.shape[0]
            object.__setattr__(self, field, arr)

    def __len__(self) -> int:
        return int(self.close.shape[0])

    def head(self, n: int) -> Bars:
        """The first ``n`` bars (used by truncation/leakage tests)."""
        return Bars(self.open[:n], self.high[:n], self.low[:n], self.close[:n])

    def mirrored(self) -> Bars:
        """Price reflection ``p -> -p`` (high and low swap roles).

        Every translation-equivariant rule evaluated on the mirrored series is the exact mirror
        of the rule on the original series (a new low becomes a new high, RSI becomes
        ``100 - RSI``, …). Rules on price *ratios* (ROC, log returns) are not
        translation-equivariant; mirrored components must express them through differences
        (e.g. momentum, whose sign equals the ROC sign for positive prices).
        """
        return Bars(-self.open, -self.low, -self.high, -self.close)


@runtime_checkable
class Component(Protocol):
    """What every registered component provides."""

    name: ClassVar[str]
    role: ClassVar[Role]
    params: ClassVar[tuple[ParamSpec, ...]]


def resolve_params(
    specs: Sequence[ParamSpec], params: Mapping[str, ParamValue] | None
) -> dict[str, ParamValue]:
    """Defaults overlaid with ``params``; unknown names and invalid values raise."""
    given = dict(params or {})
    known = {p.name for p in specs}
    unknown = sorted(set(given) - known)
    if unknown:
        raise ComponentError(f"unknown parameters: {unknown}")
    return {p.name: p.coerce(given.get(p.name, p.default)) for p in specs}


class EntryComponent(ABC):
    """Base class of entry methods: boolean long/short entry signals at bar close.

    Subclasses define ``name``, ``edge_type``, ``params`` and :meth:`long_signals`. A signal
    at bar ``i`` may use data up to the close of bar ``i`` only.
    """

    name: ClassVar[str]
    role: ClassVar[Role] = "entry"
    params: ClassVar[tuple[ParamSpec, ...]] = ()
    edge_type: ClassVar[str]
    directions: ClassVar[tuple[Direction, ...]] = DIRECTIONS
    mirror: ClassVar[bool] = True
    group: ClassVar[str | None] = None  # probe group inside the edge type (stage 1)
    # "state": the condition is true on every bar it holds (thresholds, levels);
    # "event": true only on the bar the condition starts (crossovers, breakouts, flips).
    # Required for probes (components with a group).
    trigger: ClassVar[Trigger | None] = None

    @classmethod
    @abstractmethod
    def long_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        """Long entry signal per bar (``params`` already resolved)."""

    @classmethod
    def short_signals(cls, bars: Bars, params: Mapping[str, ParamValue]) -> BoolArray:
        """Short entry signal per bar. Default (mirror rule): long rule on mirrored prices.

        Components with ``mirror = False`` must override this.
        """
        if not cls.mirror:
            raise ComponentError(f"{cls.name}: mirror=False requires its own short_signals")
        return cls.long_signals(bars.mirrored(), params)

    @classmethod
    def signals(
        cls, bars: Bars, params: Mapping[str, ParamValue] | None = None
    ) -> tuple[BoolArray, BoolArray]:
        """``(long_entry, short_entry)`` boolean arrays; a disallowed direction is all False."""
        p = resolve_params(cls.params, params)
        n = len(bars)
        long_ = (
            _as_signal(cls.long_signals(bars, p), n)
            if "long" in cls.directions
            else np.zeros(n, dtype=np.bool_)
        )
        short = (
            _as_signal(cls.short_signals(bars, p), n)
            if "short" in cls.directions
            else np.zeros(n, dtype=np.bool_)
        )
        return long_, short


def _as_signal(x: BoolArray, n: int) -> BoolArray:
    arr = np.asarray(x, dtype=np.bool_)
    if arr.shape != (n,):
        raise ComponentError(f"signal has shape {arr.shape}, expected ({n},)")
    return arr


class ExitSpec(_Frozen):
    """Exit rule set consumed by the engine (T08); first hit wins. ``None`` = rule unused.

    The disaster stop is an engine constant and is not part of an exit spec.
    """

    signal_exit: bool = False  # exit on the component's exit signal at bar close
    time_exit_bars: int | None = Field(default=None, ge=1)
    sl_atr: float | None = Field(default=None, gt=0)
    tp_atr: float | None = Field(default=None, gt=0)
    trail_atr: float | None = Field(default=None, gt=0)


class ExitComponent(ABC):
    """Base class of exit methods: map resolved parameters to an :class:`ExitSpec`."""

    name: ClassVar[str]
    role: ClassVar[Role] = "exit"
    params: ClassVar[tuple[ParamSpec, ...]] = ()

    @classmethod
    @abstractmethod
    def exit_spec(cls, params: Mapping[str, ParamValue]) -> ExitSpec:
        """The exit rules for resolved ``params``."""


def has_not_mirrored_reason(doc: str | None) -> bool:
    """True if ``doc`` contains ``Not mirrored:`` followed by a non-empty reason."""
    if not doc:
        return False
    idx = doc.find(NOT_MIRRORED_MARKER)
    return idx >= 0 and bool(doc[idx + len(NOT_MIRRORED_MARKER) :].strip())
