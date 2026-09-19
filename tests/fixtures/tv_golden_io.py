"""Loader for the TradingView golden exports (``tests/fixtures/tv_golden/*.csv.gz``).

The files are TradingView "Export chart data" CSVs of
``tools/tradingview/sf_golden_indicators.pine``
(UNIX ``time``, TradingView's own OHLC, one column per plot title), stored gzip-compressed.
"""

from __future__ import annotations

import csv
import gzip
import io
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "tests" / "fixtures" / "tv_golden"
PINE_SCRIPT = REPO_ROOT / "tools" / "tradingview" / "sf_golden_indicators.pine"
BASE_COLUMNS = ("time", "open", "high", "low", "close")

# A value printed with at least this many decimals is treated as an unrounded float64 export.
FULL_PRECISION_DECIMALS = 12


@dataclass(frozen=True)
class GoldenFile:
    name: str
    columns: dict[str, np.ndarray]  # float64, NaN where the export cell is empty
    decimals: dict[str, int]  # max number of printed decimals per column

    @property
    def export_decimals(self) -> int:
        """Largest decimal count over all non-base columns = the export's precision."""
        return max(v for k, v in self.decimals.items() if k not in BASE_COLUMNS)

    @property
    def rounded(self) -> bool:
        return self.export_decimals < FULL_PRECISION_DECIMALS


def golden_files() -> list[Path]:
    return sorted(GOLDEN_DIR.glob("*.csv.gz"))


def _decimals(cell: str) -> int:
    if "e" in cell.lower():
        mantissa, exp = cell.lower().split("e")
        frac = mantissa.split(".")[1] if "." in mantissa else ""
        return max(0, len(frac) - int(exp))
    return len(cell.split(".")[1]) if "." in cell else 0


@cache
def load_golden(path: Path) -> GoldenFile:
    text = gzip.decompress(path.read_bytes()).decode("utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    header, body = rows[0], rows[1:]
    columns: dict[str, np.ndarray] = {}
    decimals: dict[str, int] = {}
    for j, name in enumerate(header):
        cells = [r[j] for r in body]
        columns[name] = np.array([float(c) if c else np.nan for c in cells], dtype=np.float64)
        decimals[name] = max((_decimals(c) for c in cells if c), default=0)
    return GoldenFile(path.name.removesuffix(".csv.gz"), columns, decimals)


def pine_plot_titles() -> list[str]:
    """Plot titles declared in the Pine script (= indicator column names of the export)."""
    src = PINE_SCRIPT.read_text(encoding="utf-8")
    return re.findall(r'^plot\(.*,\s*"([^"]+)"\)\s*$', src, flags=re.MULTILINE)
