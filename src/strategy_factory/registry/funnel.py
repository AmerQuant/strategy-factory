"""The funnel-run link in the registry (T15a, D-663): ``funnel_runs`` and ``funnel_stage_runs``.

A funnel run links its stage runs per (timeframe, stage, arm) -- the arm is the real series or its
reshuffled control (D-662). Each stage row carries its ``stage_key`` (the content hash of what the
stage run computes), so a resumed funnel skips a stage whose row is ``done`` under the same key.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, delete, insert, select, update

from strategy_factory.core.errors import RegistryError
from strategy_factory.registry.tables import funnel_runs, funnel_stage_runs

StageSlot = tuple[str, str, str]  # (timeframe, stage, arm)


@dataclass(frozen=True)
class StageRow:
    timeframe: str
    stage: str
    arm: str
    stage_key: str
    run_id: str | None
    status: str
    inputs: int | None


class FunnelRegistry:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # -- funnel runs ---------------------------------------------------------------------
    def start_funnel(
        self,
        *,
        config: Mapping[str, Any],
        config_hash: str,
        funnel_key: str,
        code_version: str,
        seed: int,
        source: str,
        control: bool,
        notes: str = "",
    ) -> uuid.UUID:
        funnel_id = uuid.uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                insert(funnel_runs).values(
                    id=funnel_id,
                    config=dict(config),
                    config_hash=config_hash,
                    funnel_key=funnel_key,
                    code_version=code_version,
                    seed=seed,
                    source=source,
                    control=control,
                    status="running",
                    notes=notes,
                )
            )
        return funnel_id

    def resumable(self, funnel_key: str) -> uuid.UUID | None:
        """The latest unfinished funnel run with this key (``running`` or ``failed``)."""
        with self.engine.connect() as conn:
            row = conn.execute(
                select(funnel_runs.c.id)
                .where(funnel_runs.c.funnel_key == funnel_key)
                .where(funnel_runs.c.status.in_(("running", "failed")))
                .order_by(funnel_runs.c.started_at.desc())
                .limit(1)
            ).first()
        return None if row is None else uuid.UUID(str(row[0]))

    def funnel(self, funnel_id: uuid.UUID) -> dict[str, Any]:
        with self.engine.connect() as conn:
            row = conn.execute(select(funnel_runs).where(funnel_runs.c.id == funnel_id)).first()
        if row is None:
            raise RegistryError(f"unknown funnel run {funnel_id}", stage="registry")
        return dict(row._mapping)

    def reopen(self, funnel_id: uuid.UUID) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(funnel_runs)
                .where(funnel_runs.c.id == funnel_id)
                .values(status="running", finished_at=None)
            )

    def finish_funnel(self, funnel_id: uuid.UUID, status: str) -> None:
        if status not in ("done", "failed", "aborted"):
            raise RegistryError(f"invalid final funnel status {status!r}", stage="registry")
        with self.engine.begin() as conn:
            res = conn.execute(
                update(funnel_runs)
                .where(funnel_runs.c.id == funnel_id)
                .values(status=status, finished_at=dt.datetime.now(dt.UTC))
            )
        if res.rowcount != 1:
            raise RegistryError(f"unknown funnel run {funnel_id}", stage="registry")

    # -- stage runs ----------------------------------------------------------------------
    def stages(self, funnel_id: uuid.UUID) -> dict[StageSlot, StageRow]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(funnel_stage_runs).where(funnel_stage_runs.c.funnel_run_id == funnel_id)
            ).all()
        out: dict[StageSlot, StageRow] = {}
        for r in rows:
            m = r._mapping
            out[(m["timeframe"], m["stage"], m["arm"])] = StageRow(
                timeframe=m["timeframe"],
                stage=m["stage"],
                arm=m["arm"],
                stage_key=m["stage_key"],
                run_id=None if m["run_id"] is None else str(m["run_id"]),
                status=m["status"],
                inputs=m["inputs"],
            )
        return out

    def start_stage(
        self, funnel_id: uuid.UUID, slot: StageSlot, stage_key: str, inputs: int | None
    ) -> None:
        """(Re)start a stage row: an earlier row for the slot is replaced."""
        tf, stage, arm = slot
        key = (
            (funnel_stage_runs.c.funnel_run_id == funnel_id)
            & (funnel_stage_runs.c.timeframe == tf)
            & (funnel_stage_runs.c.stage == stage)
            & (funnel_stage_runs.c.arm == arm)
        )
        with self.engine.begin() as conn:
            conn.execute(delete(funnel_stage_runs).where(key))
            conn.execute(
                insert(funnel_stage_runs).values(
                    funnel_run_id=funnel_id,
                    timeframe=tf,
                    stage=stage,
                    arm=arm,
                    stage_key=stage_key,
                    status="running",
                    inputs=inputs,
                )
            )

    def set_stage_run(self, funnel_id: uuid.UUID, slot: StageSlot, run_id: str) -> None:
        self._update(funnel_id, slot, run_id=uuid.UUID(run_id))

    def finish_stage(self, funnel_id: uuid.UUID, slot: StageSlot, status: str) -> None:
        if status not in ("done", "failed", "empty"):
            raise RegistryError(f"invalid final stage status {status!r}", stage="registry")
        self._update(funnel_id, slot, status=status, finished_at=dt.datetime.now(dt.UTC))

    def _update(self, funnel_id: uuid.UUID, slot: StageSlot, **values: Any) -> None:
        tf, stage, arm = slot
        with self.engine.begin() as conn:
            res = conn.execute(
                update(funnel_stage_runs)
                .where(funnel_stage_runs.c.funnel_run_id == funnel_id)
                .where(funnel_stage_runs.c.timeframe == tf)
                .where(funnel_stage_runs.c.stage == stage)
                .where(funnel_stage_runs.c.arm == arm)
                .values(**values)
            )
        if res.rowcount != 1:
            raise RegistryError(f"unknown funnel stage {slot} of {funnel_id}", stage="registry")
