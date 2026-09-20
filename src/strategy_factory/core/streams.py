"""Stream guards (D-355, D-357): path ownership, ID discipline, one Alembic head.

Two Claude Code sessions work on this repository at the same time. The rules are in
``docs/streams/PROTOCOL.md``; the machine-readable ownership list is
``docs/streams/ownership.yaml``. ``sfac streams check`` runs the three guards in CI:

1. **Path ownership** -- a branch named ``a/...`` or ``b/...`` may not change a path owned by
   the other stream.
2. **ID discipline** -- every ``D-nnn`` / ``P-nn`` row a branch *adds* must be unique and
   inside the adding stream's range, or inside one of the **supervisor's** decision ranges,
   which any stream may carry because the supervisor dictates those. An unprefixed
   (grandfathered) branch is checked for duplicates only.
3. **One Alembic head** -- the migration graph has exactly one head, so two streams cannot
   both add a migration.

:func: is the session-start check of D-357 (1) and (5): every session works in
its **own worktree on its own branch** and may never switch the checkout of a folder it does
not own.

Every function here is pure: the caller supplies the changed paths, the added rows and the
migration files. :mod:`strategy_factory.core.cli_streams` collects them from git.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePath
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from strategy_factory.core.errors import ConfigError

DEFAULT_OWNERSHIP = Path("docs") / "streams" / "ownership.yaml"
StreamName = Literal["A", "B"]
#: A decisions-log or pending row: ``| D-357 | ...`` / ``| P-40 | ...``.
ID_ROW = re.compile(r"^\|\s*(?P<kind>[DP])-(?P<number>\d+)\s*\|")
_REVISION = re.compile(r"^revision(?::\s*str)?\s*=\s*['\"](?P<id>[^'\"]+)['\"]", re.MULTILINE)
_DOWN = re.compile(
    r"^down_revision(?::\s*[^=]+)?\s*=\s*(?:['\"](?P<id>[^'\"]+)['\"]|None)", re.MULTILINE
)


class StreamSpec(BaseModel):
    """One stream's branch prefix and ID ranges."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    branch_prefix: str = Field(min_length=2)
    folder: str = ""  # D-357 (1): the only folder this stream may work in
    decisions: tuple[int, int]
    pending: tuple[int, int]

    @model_validator(mode="after")
    def _ordered(self) -> StreamSpec:
        for label, lo_hi in (("decisions", self.decisions), ("pending", self.pending)):
            if lo_hi[0] > lo_hi[1]:
                raise ValueError(f"{self.name}: {label} range {lo_hi} is inverted")
        return self

    def covers(self, kind: str, number: int) -> bool:
        lo, hi = self.decisions if kind == "D" else self.pending
        return lo <= number <= hi


class SupervisorRange(BaseModel):
    """The supervisor's own decision ranges (D-355): allowed from any branch.

    There is more than one because a range can be used up: ``D-355 … D-359`` was, so
    ``D-600 … D-699`` was added next to it. Decisions only -- a ``P-`` number always belongs
    to the stream that raised the question.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decisions: tuple[tuple[int, int], ...]

    @field_validator("decisions", mode="before")
    @classmethod
    def _as_ranges(cls, value: Any) -> Any:
        """Accept one ``[lo, hi]`` pair as well as a list of them."""
        if isinstance(value, (list, tuple)) and value and all(isinstance(v, int) for v in value):
            return (tuple(value),)
        return value

    @model_validator(mode="after")
    def _ordered(self) -> SupervisorRange:
        if not self.decisions:
            raise ValueError("the supervisor needs at least one decision range")
        for lo, hi in self.decisions:
            if lo > hi:
                raise ValueError(f"supervisor decision range ({lo}, {hi}) is inverted")
        return self

    def covers(self, kind: str, number: int) -> bool:
        return kind == "D" and any(lo <= number <= hi for lo, hi in self.decisions)

    def describe(self) -> str:
        return " and ".join(f"D-{lo} … D-{hi}" for lo, hi in self.decisions)


class Ownership(BaseModel):
    """``docs/streams/ownership.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    supervisor: SupervisorRange | None = None
    streams: dict[str, StreamSpec]
    owners: dict[str, str]
    append_only: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _known_owners(self) -> Ownership:
        unknown = sorted({o for o in self.owners.values() if o not in self.streams})
        if unknown:
            raise ValueError(f"owners name unknown streams: {unknown}")
        prefixes = [s.branch_prefix for s in self.streams.values()]
        if len(set(prefixes)) != len(prefixes):
            raise ValueError("two streams share a branch prefix")
        return self

    def owner_of(self, path: str) -> str | None:
        """The stream owning ``path``, by longest matching prefix; ``None`` = shared."""
        best: tuple[int, str | None] = (-1, None)
        for pattern, owner in self.owners.items():
            if (path == pattern or path.startswith(pattern)) and len(pattern) > best[0]:
                best = (len(pattern), owner)
        return best[1]

    def stream_of_branch(self, branch: str) -> str | None:
        """``"A"`` / ``"B"`` from the branch prefix; ``None`` for a grandfathered branch."""
        for key, spec in self.streams.items():
            if branch.startswith(spec.branch_prefix):
                return key
        return None


def load_ownership(path: Path | None = None) -> Ownership:
    target = path if path is not None else DEFAULT_OWNERSHIP
    if not target.is_file():
        raise ConfigError("stream ownership file not found", config_path=target)
    try:
        return Ownership.model_validate(yaml.safe_load(target.read_text(encoding="utf-8")) or {})
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read stream ownership: {exc}", config_path=target) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid stream ownership: {exc}", config_path=target) from exc


# --------------------------------------------------------------------------------------
# Guard 1: path ownership
# --------------------------------------------------------------------------------------
def check_paths(stream: str | None, changed: Iterable[str], ownership: Ownership) -> list[str]:
    """Problems when ``stream``'s branch changes paths owned by the other stream (D-357 (2))."""
    if stream is None:  # grandfathered branch: not checked
        return []
    problems = []
    for path in sorted(set(changed)):
        owner = ownership.owner_of(path)
        if owner is not None and owner != stream:
            problems.append(
                f"{path}: owned by stream {owner} ({ownership.streams[owner].name}); "
                f"stream {stream} may not change it -- raise a P- question instead (D-357)"
            )
    return problems


# --------------------------------------------------------------------------------------
# Guard 2: ID discipline
# --------------------------------------------------------------------------------------
def parse_ids(rows: Iterable[str]) -> list[tuple[str, int]]:
    """``[("D", 357), ("P", 40), ...]`` for every decisions/pending table row in ``rows``."""
    out = []
    for row in rows:
        m = ID_ROW.match(row.strip())
        if m:
            out.append((m.group("kind"), int(m.group("number"))))
    return out


def check_ids(
    stream: str | None,
    added_rows: Iterable[str],
    existing_rows: Iterable[str],
    ownership: Ownership,
) -> list[str]:
    """Problems with the IDs a branch adds: duplicates, or outside the stream's range."""
    added = parse_ids(added_rows)
    existing = set(parse_ids(existing_rows))
    problems: list[str] = []
    seen: set[tuple[str, int]] = set()
    for kind, number in added:
        label = f"{kind}-{number}"
        if (kind, number) in existing or (kind, number) in seen:
            problems.append(f"{label}: duplicate id (it already exists)")
        seen.add((kind, number))
        if stream is None:  # grandfathered branch: duplicates only
            continue
        if ownership.supervisor is not None and ownership.supervisor.covers(kind, number):
            continue  # a decision the supervisor dictated (D-355): any stream may carry it
        spec = ownership.streams[stream]
        if not spec.covers(kind, number):
            lo, hi = spec.decisions if kind == "D" else spec.pending
            extra = ""
            if ownership.supervisor is not None and kind == "D":
                extra = f"; the supervisor's range is {ownership.supervisor.describe()}"
            problems.append(
                f"{label}: outside stream {stream}'s range {kind}-{lo} … {kind}-{hi} (D-355){extra}"
            )
    return problems


# --------------------------------------------------------------------------------------
# Guard 3: one Alembic head
# --------------------------------------------------------------------------------------
def alembic_heads(migrations: Mapping[str, str]) -> list[str]:
    """Head revisions of ``{filename: source}``; a head is a revision nothing points back to."""
    revisions: dict[str, str | None] = {}
    for name, source in migrations.items():
        rev = _REVISION.search(source)
        if rev is None:
            raise ConfigError(f"{name}: no `revision = ...` line")
        down = _DOWN.search(source)
        revisions[rev.group("id")] = down.group("id") if down else None
    parents = {d for d in revisions.values() if d is not None}
    return sorted(r for r in revisions if r not in parents)


def check_single_head(migrations: Mapping[str, str]) -> list[str]:
    """Problems when the migration graph does not have exactly one head (D-357 (4))."""
    if not migrations:
        return ["no Alembic migrations found"]
    heads = alembic_heads(migrations)
    if len(heads) == 1:
        return []
    return [
        f"the migration graph has {len(heads)} heads ({', '.join(heads)}); "
        "two streams may not add a migration in parallel (D-357)"
    ]


def read_migrations(versions_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(versions_dir.glob("*.py"))}


# --------------------------------------------------------------------------------------
# All three
# --------------------------------------------------------------------------------------
def check_all(
    branch: str,
    changed: Sequence[str],
    added_rows: Sequence[str],
    existing_rows: Sequence[str],
    migrations: Mapping[str, str],
    ownership: Ownership,
) -> dict[str, list[str]]:
    """``{guard: problems}`` for the three guards; every list empty means the branch is clean."""
    stream = ownership.stream_of_branch(branch)
    return {
        "paths": check_paths(stream, changed, ownership),
        "ids": check_ids(stream, added_rows, existing_rows, ownership),
        "alembic": check_single_head(migrations),
    }


# --------------------------------------------------------------------------------------
# Session start: the folder and the branch must match the stream (D-357 (1) and (5))
# --------------------------------------------------------------------------------------
def stream_of_folder(folder: str, ownership: Ownership) -> str | None:
    """The stream that owns the worktree folder ``folder``; ``None`` = nobody's (D-357 (1)).

    ``folder`` is matched on its **last path component**, so any parent directory works.
    A folder no stream owns is a spawned or helper session's own worktree, which is exactly
    what D-357 (1) asks for.
    """
    name = PurePath(folder.replace("\\", "/")).name
    for key, spec in ownership.streams.items():
        if spec.folder and spec.folder == name:
            return key
    return None


def check_session(
    folder: str, branch: str, ownership: Ownership, stream: str | None = None
) -> list[str]:
    """Problems with where this session is working (D-357 (1), checked at session start).

    ``stream`` is the stream the session claims to be; ``None`` for a spawned or helper
    session, which must be in a folder no stream owns.

    The rule this enforces: **every session works in its own worktree on its own branch, and
    may never switch the checkout of a folder it does not own.** A session sitting in another
    stream's folder is the failure mode that cost stream A a mid-task branch switch.
    """
    problems: list[str] = []
    owner = stream_of_folder(folder, ownership)
    branch_stream = ownership.stream_of_branch(branch)
    if stream is not None and stream not in ownership.streams:
        return [f"unknown stream {stream!r}; known: {sorted(ownership.streams)}"]

    if stream is None:
        if owner is not None:
            problems.append(
                f"this folder belongs to stream {owner} ({ownership.streams[owner].name}); a "
                "spawned or helper session needs its own worktree -- "
                "`git worktree add <path> -b a/<task> origin/main` (D-357 (1))"
            )
    elif owner is None:
        problems.append(
            f"stream {stream} works in {ownership.streams[stream].folder!r}, but this worktree "
            f"is {PurePath(folder.replace(chr(92), '/')).name!r} (D-357 (1))"
        )
    elif owner != stream:
        problems.append(
            f"this folder belongs to stream {owner}, not stream {stream}; never switch the "
            "checkout of a folder you do not own (D-357 (1))"
        )

    if branch_stream is not None and stream is not None and branch_stream != stream:
        problems.append(
            f"branch {branch!r} belongs to stream {branch_stream}, not stream {stream} (D-357)"
        )
    if branch_stream is not None and stream is None and owner is not None:
        problems.append(f"branch {branch!r} carries stream {branch_stream}'s prefix")
    return problems
