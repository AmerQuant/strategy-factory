"""D-377: every text-mode subprocess and file access declares its encoding.

The work happens on Windows (locale codec cp1252) and CI runs Ubuntu (UTF-8), so a text
call that relies on the locale default passes CI and fails -- or silently misreads -- on the
development machine (#33's `log₁₀`, P-52's dirty checkout read as clean). The guard is a
**static** scan of the source, so it fails on any platform, CI included.

A call site may be exempted only through ``ALLOWED`` below: by file and kind, with the reason,
and the test fails when an exempted site is fixed or gone, so the list only shrinks.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCANNED = ("src", "tests", "scripts")

SUBPROCESS_TEXT_CALLS = {"run", "check_output", "Popen", "call", "check_call"}
#: these always decode with the locale codec and take no ``encoding``
LOCALE_ONLY_CALLS = {
    ("subprocess", "getoutput"),
    ("subprocess", "getstatusoutput"),
    ("os", "popen"),
}
TEMPFILE_CALLS = {"NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile"}

#: (repo-relative path, kind) -> number of sites exempted, with the reason.
#: Stream B's paths (the data layer and its T04f script, D-357) are listed for stream B to fix;
#: stream A does not edit them (D-377).
ALLOWED: dict[tuple[str, str], tuple[int, str]] = {}


def _kw(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


#: where ``encoding`` sits when passed positionally: ``Path.read_text(encoding)``,
#: ``Path.write_text(data, encoding)``, ``open(file, mode, buffering, encoding)``,
#: ``Path.open(mode, buffering, encoding)``
ENCODING_POSITION = {"read_text": 0, "write_text": 1, "open": 3, ".open": 2}


def _declares(call: ast.Call, position: int | None) -> bool:
    if _kw(call, "encoding") is not None:
        return True
    return position is not None and len(call.args) > position


def _is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _binary_mode(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and "b" in node.value


def offences(source: str) -> list[tuple[int, str]]:
    """``(line, kind)`` for every text-mode call that leaves the encoding to the locale."""
    found: list[tuple[int, str]] = []
    for call in ast.walk(ast.parse(source)):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        attr = func.attr if isinstance(func, ast.Attribute) else None
        owner = func.value.id if attr and isinstance(func.value, ast.Name) else None  # type: ignore[union-attr]
        name = attr if attr else (func.id if isinstance(func, ast.Name) else None)
        if isinstance(func, ast.Attribute) and attr == "open":
            position = ENCODING_POSITION[".open"]
        else:
            position = ENCODING_POSITION.get(name or "")
        declared = _declares(call, position)
        kind: str | None = None
        if (owner, attr) in LOCALE_ONLY_CALLS:
            kind = f"{owner}.{attr}"
        elif owner == "subprocess" and attr in SUBPROCESS_TEXT_CALLS:
            text = _is_true(_kw(call, "text")) or _is_true(_kw(call, "universal_newlines"))
            if text and not declared:
                kind = f"subprocess.{attr}"
        elif name in ("read_text", "write_text") and not declared:
            kind = name
        elif name == "open" and not declared:
            # builtin open(file, mode, ...) or Path.open(mode, ...)
            mode = _kw(call, "mode")
            mode_at = 1 if isinstance(func, ast.Name) else 0
            if mode is None and len(call.args) > mode_at:
                mode = call.args[mode_at]
            if not _binary_mode(mode):
                kind = "open" if isinstance(func, ast.Name) else ".open"
        elif name in TEMPFILE_CALLS and not declared:
            mode = _kw(call, "mode")
            if mode is not None and not _binary_mode(mode):  # the default mode is binary
                kind = name
        if kind is not None:
            found.append((call.lineno, kind))
    return found


def scan() -> dict[tuple[str, str], list[int]]:
    sites: dict[tuple[str, str], list[int]] = {}
    for folder in SCANNED:
        for path in sorted((REPO / folder).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(REPO).as_posix()
            for line, kind in offences(path.read_text(encoding="utf-8")):
                sites.setdefault((rel, kind), []).append(line)
    return sites


# -- the scanner itself ------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('subprocess.run(["git"], capture_output=True, text=True)', "subprocess.run"),
        ('subprocess.check_output(["git"], universal_newlines=True)', "subprocess.check_output"),
        ('subprocess.Popen(["git"], stdout=PIPE, text=True)', "subprocess.Popen"),
        ('subprocess.getoutput("git status")', "subprocess.getoutput"),
        ('os.popen("git status")', "os.popen"),
        ("p.read_text()", "read_text"),
        ('p.write_text("x")', "write_text"),
        ('open("f.txt")', "open"),
        ('open("f.txt", "w")', "open"),
        ('open("f.txt", mode="r")', "open"),
        ('open("f.txt", "r", -1)', "open"),  # buffering is not an encoding
        ('p.open("r", -1)', ".open"),
        ("p.open()", ".open"),
        ('p.open("a")', ".open"),
        ('tempfile.NamedTemporaryFile(mode="w")', "NamedTemporaryFile"),
    ],
)
def test_F_X_9_d377_the_scanner_catches_each_kind(source: str, expected: str) -> None:
    assert offences(source) == [(1, expected)]


@pytest.mark.parametrize(
    "source",
    [
        'subprocess.run(["git"], capture_output=True, text=True, encoding="utf-8")',
        'subprocess.run(["git"], capture_output=True)',  # bytes: nothing is decoded
        'p.read_text(encoding="utf-8")',
        'p.read_text("utf-8")',  # positional, as stream B writes it
        'p.write_text("x", "utf-8")',
        'open("f.txt", "r", -1, "utf-8")',
        'p.open("r", -1, "utf-8")',
        'p.write_text("x", encoding="utf-8", newline="\\n")',
        "p.read_bytes()",
        'open("f.bin", "rb")',
        'open("f.bin", mode="wb")',
        'p.open("rb")',
        'open("f.txt", encoding="utf-8")',
        "tempfile.NamedTemporaryFile()",  # binary by default
        'tempfile.NamedTemporaryFile(mode="w", encoding="utf-8")',
    ],
)
def test_F_X_9_d377_the_scanner_passes_declared_and_binary_calls(source: str) -> None:
    assert offences(source) == []


# -- the codebase ------------------------------------------------------------------------------
def test_F_X_9_d377_every_text_call_declares_its_encoding() -> None:
    sites = scan()
    offending = {
        f"{path}:{','.join(map(str, lines))}: {kind}"
        for (path, kind), lines in sites.items()
        if len(lines) > ALLOWED.get((path, kind), (0, ""))[0]
    }
    assert not offending, (
        "declare encoding= on these calls (D-377) -- the locale default is cp1252 on "
        "Windows and UTF-8 on CI:\n" + "\n".join(sorted(offending))
    )


def test_F_X_9_d377_the_exemptions_are_still_needed() -> None:
    """An exemption that no longer matches a site is removed, so the list only shrinks."""
    counts = Counter({key: len(lines) for key, lines in scan().items()})
    stale = {key for key, (n, _) in ALLOWED.items() if counts[key] != n}
    assert not stale, f"update ALLOWED, these no longer match: {sorted(stale)}"
