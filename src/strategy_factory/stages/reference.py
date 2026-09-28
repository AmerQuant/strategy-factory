"""Read-only facts about a reference series that travel with a profile (D-610).

The stage gets these through :class:`ReferenceInfo` on the :class:`~stages.base.RunContext`,
never through the catalog's writers or the split manager: the class reads the catalog row,
the splice markers and the quality report of the **pinned** reference, and nothing else.

* ``quality_status`` and the codes of the checks that did not pass (``_quality/<hash>.json``);
* the splice markers (T04l, D-709) and whether the series is a research window (D-713);
* whether the snapshot is derived (T04k clean, T04l) and whether T04l trimmed it at a proven
  re-use boundary. T04l tags the notes of **both** its outputs with ``"T04l re-use"``; a
  research window (D-713) also carries a ``research_window`` splice, so a trim is the tag
  without one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from strategy_factory.data.catalog import Catalog
from strategy_factory.data.quality import QUALITY_DIR
from strategy_factory.data.schema import SeriesMetadata
from strategy_factory.stages.edge_profile import Caveat

#: The tag T04l writes into the notes of a snapshot trimmed at a re-use boundary.
T04L_TRIM_TAG = "T04l re-use"
_PASSING = {"pass", "skip", "skipped"}


class ReferenceInfo:
    """Catalog facts of reference snapshots; reads only."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    def reference(self, symbol: str, timeframe: str) -> SeriesMetadata:
        return self._catalog.get_reference(symbol, timeframe)

    def _quality_report(self, meta: SeriesMetadata) -> dict[str, Any] | None:
        path = Path(self._catalog.root) / QUALITY_DIR / f"{meta.snapshot_hash}.json"
        if not path.is_file():
            return None
        loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return loaded

    def caveats(self, symbol: str, timeframe: str) -> Caveat:
        meta = self.reference(symbol, timeframe)
        key = meta.key()
        report = self._quality_report(meta)
        failing: tuple[str, ...] = ()
        if report is not None:
            failing = tuple(
                sorted(
                    str(c["code"])
                    for c in report.get("checks", [])
                    if str(c.get("status")) not in _PASSING
                )
            )
        splices = self._catalog.splices(key)
        window = any(s.role == "research_window" for s in splices)
        return Caveat(
            quality_status=self._catalog.quality_status(key),
            warning_checks=failing,
            splices=tuple(
                {"role": s.role, "boundary": s.boundary.isoformat(), "reason": s.reason}
                for s in splices
            ),
            research_window=window,
            derived=meta.derived_from is not None,
            trimmed=T04L_TRIM_TAG in meta.notes and not window,
            notes=meta.notes,
        )
