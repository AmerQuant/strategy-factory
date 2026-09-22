"""Universe registry (F-0.9.1): ``configs/universe.yaml``.

One entry per symbol: ``asset_class``, ``reference_source``, ``timeframes``, ``cost_profile``
(resolved through the T06 assignments), ``calendar`` (``nyse`` / ``24x5`` / ``24x7``),
``group`` (for the cross-symbol validation later), ``tradable`` and ``broker_symbol`` (the
Moneta symbol from the generated ``configs/costs/moneta/symbol_map.csv``, T06b, D-524; ``None``
= not tradable at the broker, results report-only).

:func:`generate_universe` builds it from the existing universe lists (Alpaca daily and
hourly, Dukascopy, Yahoo aux). :func:`validate_universe` checks:

* one entry per symbol, so exactly one reference source per (symbol, timeframe);
* every tradable symbol has a cost profile, equal to the one the assignments resolve;
* where the catalog has a reference snapshot for (symbol, timeframe): it comes from the
  declared reference source and its asset class matches;
* a ``broker_symbol`` exists (``ok``) in the normalized broker table, is used once, and the
  symbol's cost profile is that broker symbol's Moneta profile.
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from strategy_factory.core.errors import ConfigError

Calendar = Literal["nyse", "24x5", "24x7"]
DEFAULT_UNIVERSE = Path("configs") / "universe.yaml"
UNIVERSE_DIR = Path("configs") / "universe"


class UniverseEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1)
    asset_class: str  # the schema's AssetClass values (checked in the validator)
    reference_source: str = Field(min_length=1)
    timeframes: tuple[str, ...]
    cost_profile: str | None = None
    calendar: Calendar
    group: str = Field(min_length=1)
    tradable: bool = True
    broker_symbol: str | None = None

    @model_validator(mode="after")
    def _checks(self) -> UniverseEntry:
        from typing import get_args

        from strategy_factory.data.schema import TIMEFRAMES, AssetClass

        if self.asset_class not in get_args(AssetClass):
            raise ValueError(f"{self.symbol}: unknown asset_class {self.asset_class!r}")
        bad = [t for t in self.timeframes if t not in TIMEFRAMES]
        if bad or not self.timeframes:
            raise ValueError(f"{self.symbol}: invalid timeframes {self.timeframes}")
        if self.tradable and not self.cost_profile:
            raise ValueError(f"{self.symbol}: tradable symbols need a cost_profile")
        return self


class Universe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_at: str = ""
    sources: tuple[str, ...] = ()
    symbols: tuple[UniverseEntry, ...]

    def by_symbol(self) -> dict[str, UniverseEntry]:
        return {e.symbol: e for e in self.symbols}

    def get(self, symbol: str) -> UniverseEntry:
        for e in self.symbols:
            if e.symbol == symbol:
                return e
        raise ConfigError(f"{symbol} is not in the universe", symbol=symbol)


def load_universe(path: Path | None = None) -> Universe:
    target = path if path is not None else DEFAULT_UNIVERSE
    if not target.is_file():
        raise ConfigError("universe file not found (sfac universe generate)", config_path=target)
    try:
        data = yaml.load(target.read_text(encoding="utf-8"), Loader=yaml.CSafeLoader) or {}
        return Universe.model_validate(data)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read universe: {exc}", config_path=target) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid universe: {exc}", config_path=target) from exc


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ConfigError("universe list not found", config_path=path)
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


CALENDAR_BY_CLASS: dict[str, Calendar] = {
    "us_equity": "nyse",
    "fx": "24x5",
    "metal": "24x5",
    "energy_cfd": "24x5",
    "index_cfd": "24x5",
    "crypto": "24x7",
}


def generate_universe(universe_dir: Path = UNIVERSE_DIR, costs_dir: Path | None = None) -> Universe:
    """Universe from the existing lists; cost profiles resolved via the T06 assignments."""
    from strategy_factory.costs.moneta import read_symbol_map
    from strategy_factory.costs.profile import load_assignments, load_profiles, resolve_profile

    cdir = costs_dir or Path("configs") / "costs"
    profiles, assignments = load_profiles(cdir), load_assignments(cdir)
    broker = read_symbol_map(cdir)

    def profile(symbol: str, cls: str) -> str:
        return resolve_profile(symbol, cls, profiles, assignments, cdir).name

    daily = {r["symbol"] for r in _rows(universe_dir / "us_equity_daily.csv")}
    hourly = {r["symbol"] for r in _rows(universe_dir / "us_equity_hourly.csv")}
    entries: list[UniverseEntry] = []
    for sym in sorted(daily | hourly):
        tfs = tuple(t for t, ok in (("1D", sym in daily), ("1H", sym in hourly)) if ok)
        entries.append(
            UniverseEntry(
                symbol=sym,
                asset_class="us_equity",
                reference_source="alpaca",
                timeframes=tfs,
                cost_profile=profile(sym, "us_equity"),
                calendar="nyse",
                group="us_equity",
                broker_symbol=broker.get(sym),
            )
        )
    for r in _rows(universe_dir / "dukascopy.csv"):
        cls = r["asset_class"]
        entries.append(
            UniverseEntry(
                symbol=r["symbol"],
                asset_class=cls,
                reference_source="dukascopy",
                timeframes=("1H", "1D"),
                cost_profile=profile(r["symbol"], cls),
                calendar=CALENDAR_BY_CLASS[cls],
                group=cls,
                broker_symbol=broker.get(r["symbol"]),
            )
        )
    for r in _rows(universe_dir / "aux_yahoo.csv"):
        # D-720: the aux series' own schedule calendar (nyse / nyse_bond -> nyse; weekdays -> 24x5)
        cal: Calendar = "24x5" if r.get("calendar") == "weekdays" else "nyse"
        entries.append(
            UniverseEntry(
                symbol=r["symbol"],
                asset_class="aux",
                reference_source="yahoo",
                timeframes=("1D",),
                cost_profile=None,
                calendar=cal,
                group="aux",
                tradable=False,
            )
        )
    return Universe(
        generated_at=dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        sources=tuple(
            (universe_dir / f).as_posix()
            for f in (
                "us_equity_daily.csv",
                "us_equity_hourly.csv",
                "dukascopy.csv",
                "aux_yahoo.csv",
            )
        ),
        symbols=tuple(entries),
    )


HEADER = """\
# Strategy Factory -- research universe (F-0.9.1). GENERATED by `sfac universe generate` from
# configs/universe/*.csv and configs/costs/assignments.yaml; regenerate instead of editing.
# Fields: asset_class, reference_source (one per symbol => one per symbol x timeframe),
# timeframes, cost_profile (T06 assignments), calendar (nyse | 24x5 | 24x7), group (for the
# cross-symbol validation later), tradable (aux series: false), broker_symbol (Moneta, T06b).
"""


def write_universe(u: Universe, path: Path = DEFAULT_UNIVERSE) -> None:
    lines = [
        HEADER,
        f"generated_at: '{u.generated_at}'",
        "sources:" if u.sources else "sources: []",
    ]
    lines += [f"  - {s}" for s in u.sources]
    lines.append("symbols:")
    for e in u.symbols:
        d: dict[str, Any] = e.model_dump()
        d["timeframes"] = list(e.timeframes)
        body = yaml.safe_dump(d, default_flow_style=True, sort_keys=False, width=10_000).strip()
        lines.append(f"  - {body}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def validate_universe(
    u: Universe, costs_dir: Path | None = None, catalog_root: Path | None = None
) -> list[str]:
    """All problems found (empty list = valid); see the module docstring."""
    from strategy_factory.costs.profile import load_assignments, load_profiles, resolve_profile

    problems: list[str] = []
    seen: dict[str, int] = {}
    for e in u.symbols:
        seen[e.symbol] = seen.get(e.symbol, 0) + 1
    problems += [
        f"{s}: listed {n} times (more than one reference source)" for s, n in seen.items() if n > 1
    ]

    cdir = costs_dir or Path("configs") / "costs"
    profiles, assignments = load_profiles(cdir), load_assignments(cdir)
    for e in u.symbols:
        if not e.tradable:
            continue
        try:
            expected = resolve_profile(e.symbol, e.asset_class, profiles, assignments, cdir).name
        except ConfigError as exc:
            problems.append(f"{e.symbol}: {exc.message}")
            continue
        if e.cost_profile != expected:
            problems.append(
                f"{e.symbol}: cost_profile {e.cost_profile!r} but assignments give {expected!r}"
            )

    problems += _broker_problems(u, cdir)

    if catalog_root is not None and (catalog_root / "catalog.parquet").is_file():
        from strategy_factory.data.catalog import Catalog

        refs = Catalog(catalog_root).table()
        refs = refs.filter(refs["is_reference"])
        entries = u.by_symbol()
        for r in refs.iter_rows(named=True):
            sym, tf = r["symbol"], r["timeframe"]
            ent = entries.get(sym)
            if ent is None:
                problems.append(f"{sym} {tf}: reference snapshot for a symbol not in the universe")
                continue
            if r["source"] != ent.reference_source:
                problems.append(
                    f"{sym} {tf}: catalog reference from {r['source']!r}, universe declares "
                    f"{ent.reference_source!r}"
                )
            if r["asset_class"] != ent.asset_class:
                problems.append(
                    f"{sym} {tf}: catalog asset_class {r['asset_class']!r}, universe "
                    f"{ent.asset_class!r}"
                )
    return problems


def _broker_problems(u: Universe, costs_dir: Path) -> list[str]:
    """Broker symbols exist and are ok in the broker table, are unique, match the profile."""
    from strategy_factory.costs.moneta import SPEC_CSV, profile_name, read_spec_csv
    from strategy_factory.costs.profile import MONETA_DIR

    flagged = [e for e in u.symbols if e.broker_symbol is not None]
    if not flagged:
        return []
    spec = {r.broker_symbol: r for r in read_spec_csv(costs_dir / MONETA_DIR / SPEC_CSV)}
    problems: list[str] = []
    seen: dict[str, str] = {}
    for e in flagged:
        b = e.broker_symbol
        assert b is not None
        row = spec.get(b)
        if row is None or row.row_status != "ok":
            problems.append(f"{e.symbol}: broker symbol {b!r} not an ok row of the broker table")
        if b in seen:
            problems.append(f"{e.symbol}: broker symbol {b!r} already used by {seen[b]}")
        seen[b] = e.symbol
        if e.cost_profile != profile_name(b):
            problems.append(
                f"{e.symbol}: broker symbol {b!r} but cost_profile {e.cost_profile!r} "
                f"(expected {profile_name(b)!r})"
            )
    return problems
