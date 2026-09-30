"""``sfac costs show <symbol>`` and ``sfac costs validate`` (F-0.2.1)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Annotated, Any

import numpy as np
import numpy.typing as npt
import typer

from strategy_factory.core.errors import DataError, SfacError
from strategy_factory.costs.arrays import HourlySpread, broker_scaled_table, hourly_spread_table
from strategy_factory.costs.profile import (
    CostProfile,
    CostsConfig,
    SpreadBrokerScaled,
    SpreadFromData,
    load_assignments,
    load_profiles,
    resolve_profile,
    universe_symbols,
    validate_all,
)

costs_app = typer.Typer(help="Cost profiles: show and validate.", no_args_is_help=True)
SPREAD_TIMEFRAME = "1H"  # from_data spreads come from the hourly snapshot
DISPLAY_ONLY = (
    "DISPLAY ONLY: whole snapshot, not restricted to the development segment "
    "(the snapshot is too short for a split, so it has no holdout); never used for backtests"
)


def _fail(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(code=1)


def _asset_class(symbol: str, cfg: CostsConfig) -> str:
    from strategy_factory.data.catalog import Catalog

    rows = Catalog().list_snapshots(symbol=symbol)
    if rows.height:
        return str(rows["asset_class"][0])
    classes = universe_symbols(cfg)
    if symbol not in classes:
        raise SfacError(f"{symbol} is neither in the catalog nor in the universe files")
    return classes[symbol]


def development_spread(symbol: str) -> tuple[dict[str, npt.NDArray[Any]], str]:
    """Hourly bars for a from_data spread: development segment, or display-only."""
    from strategy_factory.data.catalog import Catalog
    from strategy_factory.data.config import load_split_config
    from strategy_factory.data.split import (
        DataAccess,
        HistoryTooShortError,
        RegistryLedger,
        SplitManager,
    )
    from strategy_factory.data.store import SnapshotStore
    from strategy_factory.registry.engine import make_engine

    store = SnapshotStore()
    mgr = SplitManager(RegistryLedger(make_engine()), load_split_config(), store)
    try:
        return DataAccess(mgr).arrays(symbol, SPREAD_TIMEFRAME), "development segment"
    except HistoryTooShortError:
        meta = Catalog(store.root).get_reference(symbol, SPREAD_TIMEFRAME)
        k = meta.key()
        df = store.read_snapshot(k.source, k.symbol, k.timeframe, k.snapshot_hash)
        arrays = {c: df[c].to_numpy() for c in df.columns if c != "ts"}
        arrays["ts"] = df["ts"].dt.epoch("us").to_numpy()
        return arrays, DISPLAY_ONLY


def _print_profile(p: CostProfile) -> None:
    flag = "PLACEHOLDER - results using it are flagged" if p.is_placeholder else "verified"
    typer.echo(f"profile     : {p.name}  [{flag}]")
    typer.echo(f"source_note : {p.source_note}")
    if p.broker_symbol is not None:
        typer.echo(f"broker      : {p.broker_symbol} (quote {p.quote_ccy})")
    typer.echo(
        f"volume      : contract size {p.contract_size:g}, step {p.volume_step:g} lot, "
        f"min {p.min_volume:g} lot" + ("  [ASSUMED, D-314]" if p.volume_step_assumed else "")
    )
    if p.to_verify:
        typer.echo(f"to_verify   : {', '.join(p.to_verify)}")
    if p.pip_size is not None:
        typer.echo(f"pip_size    : {p.pip_size:g}")
    typer.echo(f"spread      : {p.spread.model_dump()}")
    typer.echo(f"commission  : {p.commission.model_dump()}")
    typer.echo(f"swap        : {p.swap.model_dump()}")
    typer.echo(f"slippage    : {p.slippage.model_dump()}")


def _print_table(t: HourlySpread, basis: str, pip: float | None) -> None:
    typer.echo(f"hourly full spread ({basis}):")
    head = "UTC hour | bars | median spread" + (" | pips" if pip else "")
    typer.echo(head)
    for h in range(24):
        v = float(t.full_spread[h])
        pips = f" | {v / pip:.2f}" if pip else ""
        mark = " (fallback)" if h in t.fallback_hours else ""
        typer.echo(f"{h:>8} | {int(t.counts[h]):>4} | {v:.6g}{pips}{mark}")
    if t.week_open is not None:
        pips = f" | {t.week_open / pip:.2f}" if pip else ""
        typer.echo(f"week open | {t.week_open_count:>4} | {t.week_open:.6g}{pips} (D-716)")


@costs_app.command("show")
def show_cmd(
    symbol: Annotated[str, typer.Argument(help="Canonical symbol.")],
    costs_dir: Annotated[Path | None, typer.Option(help="Cost config directory.")] = None,
) -> None:
    """Show the resolved cost profile of SYMBOL (and its hourly spread for from_data)."""
    cfg = CostsConfig() if costs_dir is None else CostsConfig(costs_dir=costs_dir)
    try:
        profiles, assignments = load_profiles(cfg.costs_dir), load_assignments(cfg.costs_dir)
        cls = _asset_class(symbol, cfg)
        prof = resolve_profile(symbol, cls, profiles, assignments, cfg.costs_dir)
        typer.echo(f"symbol      : {symbol} ({cls})")
        _print_profile(prof)
        if isinstance(prof.spread, SpreadFromData):
            try:
                bars, basis = development_spread(symbol)
            except DataError as exc:
                typer.echo(f"hourly spread table unavailable: {exc}")
                return
            if "spread" not in bars:
                raise SfacError(f"{symbol} {SPREAD_TIMEFRAME} snapshot has no spread column")
            fb = None
            if prof.spread.fallback is not None:
                a = prof.spread.fallback
                fb = a.value * (prof.pip_size or 1.0) if a.unit == "pip" else a.value
            table = hourly_spread_table(
                np.asarray(bars["ts"], dtype=np.int64),
                np.asarray(bars["spread"], dtype=np.float64),
                prof.spread.scale,
                fb,
            )
            _print_table(table, basis, prof.pip_size)
        elif isinstance(prof.spread, SpreadBrokerScaled):
            try:
                bars, basis = development_spread(symbol)
            except DataError as exc:
                typer.echo(f"hourly spread table unavailable: {exc}")
                return
            if "spread" not in bars:
                typer.echo("no spread column: the broker spread is used as a fixed spread")
                return
            ts = np.asarray(bars["ts"], dtype=np.int64)
            sp = np.asarray(bars["spread"], dtype=np.float64)
            _print_table(
                hourly_spread_table(ts, sp, 1.0, np.nan), f"{basis}, unscaled", prof.pip_size
            )
            scaled, factor = broker_scaled_table(ts, sp, prof.spread.broker_spread)
            _print_table(scaled, f"{basis}, scaled x {factor:.6g}", prof.pip_size)
            mean = scaled.bar_weighted_mean()
            typer.echo(
                f"bar-weighted mean after scaling: {mean:.6g} "
                f"(broker spread {prof.spread.broker_spread:.6g})"
            )
    except SfacError as exc:
        raise _fail(str(exc)) from exc


@costs_app.command("validate")
def validate_cmd(
    costs_dir: Annotated[Path | None, typer.Option(help="Cost config directory.")] = None,
) -> None:
    """Every universe symbol has a profile; every profile and override is valid."""
    cfg = CostsConfig() if costs_dir is None else CostsConfig(costs_dir=costs_dir)
    try:
        assigned, missing = validate_all(cfg)
        profiles = load_profiles(cfg.costs_dir)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    for name, n in sorted(Counter(assigned.values()).items()):
        status = profiles[name].status
        typer.echo(f"{name:<22} {n:>6} symbol(s)  [{status}]")
    if missing:
        shown = ", ".join(missing[:20]) + (" ..." if len(missing) > 20 else "")
        raise _fail(f"{len(missing)} universe symbol(s) without a cost profile: {shown}")
    placeholders = sum(1 for p in profiles.values() if p.is_placeholder)
    typer.echo(
        f"ok: {len(assigned)} symbols assigned, {len(profiles)} profiles "
        f"({placeholders} placeholder)"
    )


moneta_app = typer.Typer(
    help="Moneta broker file: import and build profiles.", no_args_is_help=True
)
costs_app.add_typer(moneta_app, name="moneta")
REVIEW_CSV = Path("docs") / "reviews" / "T06b_mapping_review.csv"


@moneta_app.command("import")
def moneta_import_cmd(
    xlsx: Annotated[
        Path | None, typer.Option(help="Broker xlsx (default: from moneta.yaml).")
    ] = None,
    costs_dir: Annotated[Path | None, typer.Option(help="Cost config directory.")] = None,
) -> None:
    """Parse the broker xlsx into configs/costs/moneta/moneta_spec.csv (+ SHA-256 sidecar)."""
    from strategy_factory.costs.moneta import import_spec, load_moneta_config
    from strategy_factory.data.download.rawfiles import raw_root

    cfg = CostsConfig() if costs_dir is None else CostsConfig(costs_dir=costs_dir)
    mdir = cfg.costs_dir / "moneta"
    try:
        mcfg = load_moneta_config(mdir)
        root = raw_root()
        path = xlsx if xlsx is not None else root / mcfg.source.spec_file
        try:
            label = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise SfacError(f"the broker file must be under SFAC_RAW_ROOT (D-028): {path}") from exc
        rep = import_spec(path, mdir, source_label=label, file_date=mcfg.source.file_date)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"source  : {label}")
    typer.echo(f"sha256  : {rep.sha256}")
    for sheet, n in rep.counts.items():
        typer.echo(f"{sheet:<14} {n:>4} rows")
    typer.echo("status  : " + ", ".join(f"{k} {v}" for k, v in sorted(rep.status_counts.items())))
    for r in rep.not_ok:
        typer.echo(f"  {r.row_status:<10} {r.sheet}!{r.row} {r.broker_symbol}: {r.status_reason}")


@moneta_app.command("build")
def moneta_build_cmd(
    costs_dir: Annotated[Path | None, typer.Option(help="Cost config directory.")] = None,
    review_csv: Annotated[Path, typer.Option(help="Mapping review CSV for the user.")] = REVIEW_CSV,
) -> None:
    """Map broker <-> research symbols and generate the Moneta profiles and assignments."""
    from strategy_factory.costs.moneta import build
    from strategy_factory.data.download.rawfiles import raw_root

    cfg = CostsConfig() if costs_dir is None else CostsConfig(costs_dir=costs_dir)
    try:
        res = build(cfg.costs_dir, raw_root(), universe_symbols(cfg), review_csv)
    except SfacError as exc:
        raise _fail(str(exc)) from exc
    methods = Counter(m.method for m in res.mapping.mapped)
    review = Counter(v.status for v in res.mapping.review)
    typer.echo(f"mapped  : {len(res.mapping.mapped)} ({dict(sorted(methods.items()))})")
    typer.echo(f"review  : {dict(sorted(review.items()))} -> {review_csv.as_posix()}")
    typer.echo(f"profiles: {len(res.profiles)} (1 proxy + {len(res.profiles) - 1} broker)")
    for sym, notes in sorted(res.to_verify.items()):
        typer.echo(f"  to_verify {sym}: {', '.join(notes)}")
