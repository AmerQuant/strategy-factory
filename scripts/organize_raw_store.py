"""T00b / F-0.1.12 -- build the immutable raw data store from byte-identical copies.

Selects source files from the group definitions in ``docs/data_inventory.json`` (T00/T00b),
copies them byte-for-byte (no conversion, no renaming) into
``SFAC_RAW_ROOT/<asset_class>/<source>_<variant>/<timeframe>/``, verifies every copy with
sha256, marks copies read-only and writes a copy manifest plus ``README.md``.

Rules:
* Source folders are only read. Every file under the source roots is stat-ed (size + mtime)
  before and after the run; any change aborts with a non-zero exit code.
* Idempotent: an existing identical destination file is skipped; an existing *different*
  destination file is an error (never overwritten).
* Free disk space is checked before copying.

Run (roots from arguments or the repo ``.env``):

    uv run --with polars python scripts/organize_raw_store.py [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = REPO / "docs" / "data_inventory.json"

# (inventory group id, destination under raw/) -- the decided copy list (T00b task, step 2)
COPY_PLAN: list[tuple[str, tuple[str, ...]]] = [
    ("MS-US-1D", ("us_equity", "alpaca_sip_all", "1D")),
    ("MS-CRYPTO-1D", ("crypto", "binance", "1D")),
    ("MS-PIT-CRYPTO-1D", ("crypto", "binance_pit", "1D")),
    ("MS-IRAN-1D", ("iran", "tsetmc", "1D")),
    ("QP-REF", ("reference", "quantplatform")),
    ("ATM-FUT-1H", ("futures", "tradestation", "1H")),
]
# Single reference files next to the MarketScanner candles folder (not an inventory group)
MS_REFERENCE_FILES = ("symbols.csv", "iran_meta.csv")
MS_REFERENCE_DEST = ("reference", "marketscanner")

NOT_IMPORTED: list[tuple[str, str]] = [
    (
        "QP-US-EQ-1D",
        "Alpaca IEX feed (volume ≈1–4% of SIP), two timestamp conventions; superseded by the Alpaca SIP split-adjusted download (T04a).",
    ),
    (
        "QP-US-EQ-1H",
        "Alpaca IEX feed, not RTH-filtered; superseded by the Alpaca SIP hourly download (T04a).",
    ),
    (
        "QP-STOOQ-1H",
        "Stooq hourly: only ≈2 years, not dividend-adjusted, half-day binning unclear; superseded by Alpaca SIP hourly.",
    ),
    (
        "QP-CRYPTO-1H",
        "binanceus hourly, thin venue; crypto is P2 and Binance global daily is kept instead.",
    ),
    (
        "ME-FUT-15M",
        "old 15-minute futures ending 2023-11-01; superseded by ATM-FUT-1H (same feed, to 2025-07-09).",
    ),
    (
        "ATM-FUT-1440",
        "not in the decided copy list (only 1H futures); question open which daily variant to use.",
    ),
    (
        "ATM-FUT-DAILY",
        "not in the decided copy list (only 1H futures); question open which daily variant to use.",
    ),
    (
        "ATM `.txt` twins",
        "byte-identical duplicates of the `.csv` files (sha256-verified in the inventory).",
    ),
    (
        "ATM `- Copy` / `.bak` files",
        "manually edited copies without the header block, and backups; do not fit the group pattern.",
    ),
]
PLACEHOLDERS: list[tuple[tuple[str, ...], str]] = [
    (("us_equity", "alpaca_sip_split", "1D"), "Alpaca SIP daily, adjustment=split (T04a)"),
    (("us_equity", "alpaca_sip_split", "1H"), "Alpaca SIP hourly, adjustment=split (T04a)"),
    (("fx_metals_cfd", "dukascopy"), "Dukascopy bid/ask h1 + m1 via dukascopy-node (T04b)"),
    (("aux", "yahoo", "1D"), "Yahoo auxiliary daily series (T04c)"),
    (("_reports",), "download/check reports written by the tools"),
]
SPACE_MARGIN_BYTES = 1 << 30  # keep at least 1 GiB free after copying
CHUNK = 1 << 20


class CopyConflictError(RuntimeError):
    """A destination file exists but differs from its source (never overwritten)."""


class IntegrityError(RuntimeError):
    """A source file changed during the run, or a copy does not verify."""


@dataclass(frozen=True)
class CopyResult:
    status: str  # "copied" | "identical"
    sha256: str
    size_bytes: int


# --------------------------------------------------------------------------------------
# Core copy / verify logic (unit-tested)
# --------------------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def make_read_only(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def is_read_only(path: Path) -> bool:
    return not os.access(path, os.W_OK)


def copy_verified(src: Path, dest: Path, src_sha: str | None = None) -> CopyResult:
    """Copy ``src`` to ``dest`` byte-for-byte, verify sha256, set read-only.

    Existing identical ``dest`` -> skipped (``identical``); existing different ``dest`` ->
    :class:`CopyConflictError`. The copy goes to a temporary file first and is renamed only
    after its hash matches the source.
    """
    src_sha = src_sha or sha256_file(src)
    size = src.stat().st_size
    if dest.exists():
        if dest.stat().st_size == size and sha256_file(dest) == src_sha:
            if not is_read_only(dest):
                make_read_only(dest)
            return CopyResult("identical", src_sha, size)
        raise CopyConflictError(
            f"destination exists and differs from source: {dest} (source {src})"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    if tmp.exists():
        tmp.chmod(stat.S_IWUSR | stat.S_IRUSR)
        tmp.unlink()
    shutil.copyfile(src, tmp)
    tmp_sha = sha256_file(tmp)
    if tmp_sha != src_sha:
        tmp.unlink()
        raise IntegrityError(f"copy does not verify: {src} -> {dest}")
    os.replace(tmp, dest)
    make_read_only(dest)
    return CopyResult("copied", src_sha, size)


def snapshot_files(paths: list[Path]) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for p in paths:
        st = p.stat()
        out[str(p)] = (st.st_size, st.st_mtime_ns)
    return out


def snapshot_roots(roots: list[Path]) -> dict[str, tuple[int, int]]:
    files = [p for r in roots if r.exists() for p in r.rglob("*") if p.is_file()]
    return snapshot_files(files)


def compare_snapshots(
    before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]
) -> dict[str, list[str]]:
    return {
        "changed": sorted(k for k in before if k in after and before[k] != after[k]),
        "added": sorted(k for k in after if k not in before),
        "removed": sorted(k for k in before if k not in after),
    }


# --------------------------------------------------------------------------------------
# Planning from the inventory
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class PlannedFile:
    group: str
    src: Path
    dest: Path


def env_value(key: str) -> str | None:
    value = os.environ.get(key)
    dotenv = REPO / ".env"
    if not value and dotenv.is_file():
        for raw in dotenv.read_text(encoding="utf-8").splitlines():
            k, sep, v = raw.strip().partition("=")
            if sep and k.strip() == key:
                value = v.strip().strip("'\"")
    return value or None


def group_files(group: dict[str, Any]) -> list[Path]:
    root = Path(group["root"])
    found: set[Path] = set()
    for pat in group["patterns"]:
        found.update(p for p in root.glob(pat) if p.is_file())
    return sorted(found, key=lambda p: str(p).lower())


def build_plan(inventory: dict[str, Any], raw_root: Path) -> tuple[list[PlannedFile], list[str]]:
    groups = {g["group_id"]: g for g in inventory["groups"]}
    plan: list[PlannedFile] = []
    problems: list[str] = []
    for gid, dest_parts in COPY_PLAN:
        g = groups.get(gid)
        if g is None:
            problems.append(f"group {gid} missing from the inventory")
            continue
        files = group_files(g)
        if len(files) != g["file_count"]:
            problems.append(
                f"{gid}: {len(files)} files match now, inventory recorded {g['file_count']}"
            )
        root = Path(g["root"])
        dest_dir = raw_root.joinpath(*dest_parts)
        plan += [PlannedFile(gid, f, dest_dir / f.relative_to(root)) for f in files]
    ms_candles = Path(inventory["meta"]["roots"]["MarketScanner candles"])
    for name in MS_REFERENCE_FILES:
        src = ms_candles.parent / name
        if src.is_file():
            plan.append(PlannedFile("MS-REF", src, raw_root.joinpath(*MS_REFERENCE_DEST, name)))
        else:
            problems.append(f"MS-REF: {src} not found")
    return plan, problems


def unassigned_in_roots(inventory: dict[str, Any], plan: list[PlannedFile]) -> list[dict[str, str]]:
    """Files in the roots of copied groups that are not copied, with the reason."""
    groups = {g["group_id"]: g for g in inventory["groups"]}
    planned = {str(p.src) for p in plan}
    member: dict[str, str] = {}
    for gid, g in groups.items():
        if "patterns" in g and "root" in g:
            for f in group_files(g):
                member.setdefault(str(f), gid)
    roots = {Path(groups[gid]["root"]) for gid, _ in COPY_PLAN if gid in groups}
    out = []
    for root in sorted(roots):
        for f in sorted(p for p in root.iterdir() if p.is_file()):
            if str(f) in planned:
                continue
            gid = member.get(str(f))
            reason = f"member of {gid} (not imported)" if gid else "fits no group pattern"
            out.append({"file": str(f), "reason": reason})
    return out


# --------------------------------------------------------------------------------------
# Manifest + README
# --------------------------------------------------------------------------------------
MANIFEST_COLUMNS = [
    "group",
    "src_path",
    "dest_path",
    "size_bytes",
    "sha256",
    "src_mtime",
    "copied_at",
]


def write_manifest(rows: list[dict[str, Any]], manifest_dir: Path) -> None:
    import polars as pl  # only needed here; keeps the copy logic importable without polars

    manifest_dir.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(
        rows, schema={c: (pl.Int64 if c == "size_bytes" else pl.Utf8) for c in MANIFEST_COLUMNS}
    )
    df = df.sort("dest_path")
    for name, writer in (
        ("copy_manifest.parquet", df.write_parquet),
        ("copy_manifest.csv", df.write_csv),
    ):
        tmp = manifest_dir / (name + ".partial")
        writer(tmp)
        os.replace(tmp, manifest_dir / name)


def load_previous_manifest(manifest_dir: Path) -> dict[str, dict[str, Any]]:
    path = manifest_dir / "copy_manifest.parquet"
    if not path.is_file():
        return {}
    import polars as pl

    return {r["dest_path"]: r for r in pl.read_parquet(path).iter_rows(named=True)}


def readme_text(
    inventory: dict[str, Any],
    raw_root: Path,
    plan: list[PlannedFile],
    stats: dict[str, dict[str, float]],
) -> str:
    groups = {g["group_id"]: g for g in inventory["groups"]}
    lines = [
        "# Strategy Factory — raw data store (`SFAC_RAW_ROOT`)",
        "",
        "Immutable raw inputs for Strategy Factory: byte-identical copies of existing downloads (T00b) and",
        "new downloads (T04a/b/c). Canonical, validated snapshots live in `SFAC_DATA_ROOT` (the `store` folder),",
        "built from these files by the adapters.",
        "",
        "## Folder convention",
        "",
        "```",
        "raw/<asset_class>/<source>_<variant>/<timeframe>/<files as delivered by the source>",
        "raw/reference/<origin>/          reference tables (symbol lists, metadata)",
        "raw/_manifests/                  copy manifest (parquet + csv)",
        "raw/_reports/                    reports written by download/check tools",
        "```",
        "",
        "## Immutability rules",
        "",
        "- Files are copied **byte-for-byte in their original format** (no conversion, no renaming); every copy is",
        "  verified with sha256 against its source and recorded in `_manifests/copy_manifest.{parquet,csv}`.",
        "- Data files are **read-only**. Never edit, re-save or delete them. A corrected or newer version is a new file",
        "  next to the old one (downloads use new file names; the old file is kept).",
        "- Re-running `scripts/organize_raw_store.py` copies nothing when everything is present and identical; a",
        "  differing existing file is an error, never an overwrite.",
        "- The original source folders are never modified; the copy run checks size+mtime of every source file",
        "  before and after.",
        "",
        "## Provenance",
        "",
        "| folder | T00 group | original path | pattern | files | size |",
        "|---|---|---|---|---|---|",
    ]
    for gid, dest_parts in COPY_PLAN:
        g = groups.get(gid, {})
        st = stats.get(gid, {"files": 0, "bytes": 0})
        lines.append(
            f"| `{'/'.join(dest_parts)}/` | {gid} | `{g.get('root', '?')}` | "
            f"{', '.join(f'`{p}`' for p in g.get('patterns', []))} | {int(st['files'])} | {st['bytes'] / 1e9:.3f} GB |"
        )
    st = stats.get("MS-REF", {"files": 0, "bytes": 0})
    ms_parent = Path(inventory["meta"]["roots"]["MarketScanner candles"]).parent
    lines.append(
        f"| `{'/'.join(MS_REFERENCE_DEST)}/` | — (MarketScanner manifests) | `{ms_parent}` | "
        f"{', '.join(f'`{n}`' for n in MS_REFERENCE_FILES)} | {int(st['files'])} | {st['bytes'] / 1e9:.3f} GB |"
    )
    lines += [
        "",
        "Group details (source, timezone, bar labels, adjustment): `docs/data_inventory.md` in the repo.",
        "",
    ]
    lines += ["## Not imported", "", "| source group / files | reason |", "|---|---|"]
    lines += [f"| {g} | {why} |" for g, why in NOT_IMPORTED]
    lines += ["", "## Placeholders for future downloads", "", "| folder | content |", "|---|---|"]
    lines += [f"| `{'/'.join(parts)}/` | {what} |" for parts, what in PLACEHOLDERS]
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    ap.add_argument("--raw-root", type=Path, default=None, help="default: SFAC_RAW_ROOT")
    ap.add_argument("--data-root", type=Path, default=None, help="default: SFAC_DATA_ROOT")
    ap.add_argument("--dry-run", action="store_true", help="plan and check only; copy nothing")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    raw_env = env_value("SFAC_RAW_ROOT")
    data_env = env_value("SFAC_DATA_ROOT")
    raw_root = args.raw_root or (Path(raw_env) if raw_env else None)
    data_root = args.data_root or (Path(data_env) if data_env else None)
    if raw_root is None or data_root is None:
        print("[error] SFAC_RAW_ROOT and SFAC_DATA_ROOT must be set (arguments or .env)")
        return 2

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    plan, problems = build_plan(inventory, raw_root)
    if problems:
        print("[error] plan problems:\n  " + "\n  ".join(problems))
        return 2
    source_roots = [Path(v) for v in inventory["meta"]["roots"].values()]
    extra_sources = [p.src for p in plan if p.group == "MS-REF"]
    unassigned = unassigned_in_roots(inventory, plan)

    planned_bytes = sum(p.src.stat().st_size for p in plan)
    to_copy_bytes = sum(p.src.stat().st_size for p in plan if not p.dest.exists())
    probe = raw_root
    while not probe.exists():
        probe = probe.parent
    free_before = shutil.disk_usage(probe).free
    print(
        f"[plan] {len(plan)} files, {planned_bytes / 1e9:.3f} GB planned; {to_copy_bytes / 1e9:.3f} GB still to copy"
    )
    print(f"[space] free on target volume: {free_before / 1e9:.1f} GB")
    if to_copy_bytes + SPACE_MARGIN_BYTES > free_before:
        print("[error] insufficient free space on the target volume")
        return 3
    if args.dry_run:
        return 0

    before = snapshot_roots(source_roots) | snapshot_files(extra_sources)
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    previous = load_previous_manifest(raw_root / "_manifests")
    rows: list[dict[str, Any]] = []
    stats: dict[str, dict[str, float]] = {}
    counts = {"copied": 0, "identical": 0}
    errors: list[str] = []
    for i, pf in enumerate(plan, 1):
        try:
            res = copy_verified(pf.src, pf.dest)
        except (CopyConflictError, IntegrityError) as exc:
            errors.append(str(exc))
            continue
        counts[res.status] += 1
        prev = previous.get(str(pf.dest))
        rows.append(
            {
                "group": pf.group,
                "src_path": str(pf.src),
                "dest_path": str(pf.dest),
                "size_bytes": res.size_bytes,
                "sha256": res.sha256,
                "src_mtime": dt.datetime.fromtimestamp(pf.src.stat().st_mtime, dt.UTC).isoformat(
                    timespec="seconds"
                ),
                "copied_at": prev["copied_at"] if (prev and res.status == "identical") else now,
            }
        )
        s = stats.setdefault(pf.group, {"files": 0, "bytes": 0})
        s["files"] += 1
        s["bytes"] += res.size_bytes
        if i % 2000 == 0:
            print(f"  {i}/{len(plan)} ...", flush=True)
    after = snapshot_roots(source_roots) | snapshot_files(extra_sources)
    integrity = compare_snapshots(before, after)

    for parts, _ in PLACEHOLDERS:
        raw_root.joinpath(*parts).mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    write_manifest(rows, raw_root / "_manifests")
    (raw_root / "README.md").write_text(
        readme_text(inventory, raw_root, plan, stats), encoding="utf-8", newline="\n"
    )

    # verify the manifest against the files on disk (acceptance: every sha256 matches)
    mismatches = [r["dest_path"] for r in rows if sha256_file(Path(r["dest_path"])) != r["sha256"]]
    free_after = shutil.disk_usage(raw_root).free
    report = {
        "run_at": now,
        "raw_root": str(raw_root),
        "data_root": str(data_root),
        "planned_files": len(plan),
        "manifest_rows": len(rows),
        "copied": counts["copied"],
        "already_present_identical": counts["identical"],
        "errors": errors,
        "sha256_mismatches_after_copy": mismatches,
        "read_only_violations": [
            r["dest_path"] for r in rows if not is_read_only(Path(r["dest_path"]))
        ],
        "per_group": stats,
        "free_bytes_before": free_before,
        "free_bytes_after": free_after,
        "source_integrity": {k: len(v) for k, v in integrity.items()},
        "source_integrity_files": {k: v[:50] for k, v in integrity.items()},
        "source_files_checked": len(before),
        "not_copied_in_group_roots": unassigned,
    }
    rep_dir = raw_root / "_reports"
    rep_path = rep_dir / f"organize_raw_store_{now.replace(':', '').replace('-', '')}.json"
    rep_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )

    print(
        f"[copy] copied {counts['copied']}, already present+identical {counts['identical']}, errors {len(errors)}"
    )
    print(
        f"[verify] manifest rows {len(rows)} / planned {len(plan)}; sha256 mismatches {len(mismatches)}"
    )
    print(
        f"[integrity] source files checked {len(before)}: "
        + ", ".join(f"{k} {len(v)}" for k, v in integrity.items())
    )
    print(f"[space] free before {free_before / 1e9:.2f} GB, after {free_after / 1e9:.2f} GB")
    print(f"[report] {rep_path}")
    if any(integrity.values()):
        print("[STOP] source files changed during the run")
        return 4
    if errors or mismatches or len(rows) != len(plan):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
