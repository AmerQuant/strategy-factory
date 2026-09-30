"""T04j (D-661): where an instrument's Dukascopy references stand against its complete window.

The resume command (``scripts/pilots/T04j_resume.py``) asks this, per instrument, what is left:

* ``absent``: no Dukascopy 1H reference -- ingest it over its window.
* ``pilot``: the 1H reference is a hash-version-1 T04e pilot -- re-ingest with ``--rehash``.
* ``grown``: a gap closed, so the window now **starts earlier** than the 1H reference -- re-derive
  it over the longer window as a new versioned snapshot (D-661); nothing is overwritten.
* ``incomplete``: the 1H reference stands, but the 1D reference is not derived from it (D-032) or a
  quality report is missing -- derive and check, without a new ingest.
* ``ingested``: nothing to do.

Only a gap that closes re-derives an instrument. A new month at the end of the window does **not**:
D-661 does not extend the series month by month (that would move every D-008 holdout boundary and
the universe each month), so the reference keeps the window it was ingested over.
"""

from __future__ import annotations

from typing import Literal

from strategy_factory.core.errors import SfacError
from strategy_factory.data.catalog import Catalog
from strategy_factory.data.coverage import Window
from strategy_factory.data.schema import SeriesMetadata

State = Literal["absent", "pilot", "grown", "incomplete", "ingested"]


def _reference(catalog: Catalog, symbol: str, timeframe: str) -> SeriesMetadata | None:
    try:
        return catalog.get_reference(symbol, timeframe)
    except SfacError:
        return None


def reference_state(catalog: Catalog, symbol: str, window: Window | None) -> State:
    """The state of ``symbol``'s Dukascopy references against ``window`` (None: no window now)."""
    h1 = _reference(catalog, symbol, "1H")
    if h1 is None or h1.source != "dukascopy":
        return "absent"
    if h1.hash_version == 1:
        return "pilot"
    first = h1.first_ts.strftime("%Y-%m") if h1.first_ts is not None else None
    if window is not None and window.first is not None and first and window.first < first:
        return "grown"
    d1 = _reference(catalog, symbol, "1D")
    if d1 is None or d1.derived_from is None or d1.derived_from.snapshot_hash != h1.snapshot_hash:
        return "incomplete"
    if any(catalog.quality_status(m.key()) == "unchecked" for m in (h1, d1)):
        return "incomplete"
    return "ingested"
