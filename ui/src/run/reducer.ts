/**
 * The run reducer: (RunState, events) -> RunState. Everything the live monitor shows is derived from
 * it. Pure from the caller's side: the input state is never mutated.
 *
 * - An event whose `seq` was already applied is dropped (D-782, D-791): replaying the whole history
 *   after a reconnect can neither duplicate nor lose progress.
 * - A `seq` that skips ahead is applied and counted as a gap (the contract promises none).
 * - Unknown event types go to the log, never dropped (§3.1).
 * - Events are applied in batches (one copy per batch), so a long history replays in linear time.
 */
import type {
  Arm,
  CodeVersion,
  FunnelStarted,
  KnownEvent,
  PlanEntry,
  RunEvent,
  Source,
  Timeframe,
} from '../api/contract';
import { isUnknownEvent } from '../api/contract';

export type SlotStatus = 'queued' | 'running' | 'finished' | 'failed' | 'stopped';

/** One entry of the plan (stage x timeframe x arm) and its latest stage run. */
export interface Slot {
  key: string;
  stage_id: string;
  timeframe: Timeframe;
  arm: Arm;
  /** False for a stage run the events started that the plan did not list (forward compatibility). */
  planned: boolean;
  status: SlotStatus;
  reused: boolean;
  stage_run_id: string | null;
  unit_kind: string | null;
  units_done: number;
  units_total: number | null;
  elapsed_s: number | null;
  eta_s: number | null;
  n_in: number | null;
  n_passed: number | null;
  error_kind: string | null;
  message: string | null;
  /** Wall-clock start and end (event `ts`), for the Gantt. */
  started_at: string | null;
  ended_at: string | null;
  /** Times the stage was started (a resume re-runs a failed or stopped stage). */
  attempts: number;
  /** Earlier attempts that failed or were stopped, for the Gantt. */
  earlier: { started_at: string; ended_at: string; status: 'failed' | 'stopped' }[];
}

export type RunStatusView = 'connecting' | 'running' | 'finished' | 'failed' | 'stopped';

export interface RunHeader {
  name: string;
  config_id: string;
  config_hash: string;
  profile_hash: string | null;
  code_version: CodeVersion;
  source: Source;
  seed: number | null;
  control: boolean;
}

export interface RunState {
  runId: string;
  lastSeq: number;
  header: RunHeader | null;
  status: RunStatusView;
  started_at: string | null;
  last_ts: string | null;
  finished_at: string | null;
  /** The funnel's elapsed time from its terminal event. */
  elapsed_s: number | null;
  failure: { error_kind: string; message: string } | null;
  /** Slot keys in plan order (unplanned stage runs appended in order of appearance). */
  order: string[];
  slots: Record<string, Slot>;
  /** stage_run_id -> slot key */
  byStageRun: Record<string, string>;
  /** Every applied event except `progress` (those drive the slots). */
  log: RunEvent[];
  resumes: number;
  applied: number;
  duplicatesDropped: number;
  gaps: number;
}

export function slotKey(e: { stage_id: string; timeframe: string; arm: string }): string {
  return `${e.stage_id}|${e.timeframe}|${e.arm}`;
}

export function initialRunState(runId: string): RunState {
  return {
    runId,
    lastSeq: 0,
    header: null,
    status: 'connecting',
    started_at: null,
    last_ts: null,
    finished_at: null,
    elapsed_s: null,
    failure: null,
    order: [],
    slots: {},
    byStageRun: {},
    log: [],
    resumes: 0,
    applied: 0,
    duplicatesDropped: 0,
    gaps: 0,
  };
}

function emptySlot(p: PlanEntry, planned: boolean): Slot {
  return {
    key: slotKey(p),
    stage_id: p.stage_id,
    timeframe: p.timeframe,
    arm: p.arm,
    planned,
    status: 'queued',
    reused: false,
    stage_run_id: null,
    unit_kind: null,
    units_done: 0,
    units_total: null,
    elapsed_s: null,
    eta_s: null,
    n_in: null,
    n_passed: null,
    error_kind: null,
    message: null,
    started_at: null,
    ended_at: null,
    attempts: 0,
    earlier: [],
  };
}

function headerOf(e: FunnelStarted): RunHeader {
  return {
    name: e.name,
    config_id: e.config_id,
    config_hash: e.config_hash,
    profile_hash: e.profile_hash,
    code_version: e.code_version,
    source: e.source,
    seed: e.seed,
    control: e.control,
  };
}

/** Mutable working copy used inside one batch. */
interface Draft extends RunState {
  touched: Set<string>;
}

function slotForWrite(d: Draft, key: string): Slot | undefined {
  const s = d.slots[key];
  if (!s) return undefined;
  if (!d.touched.has(key)) {
    d.slots[key] = { ...s };
    d.touched.add(key);
  }
  return d.slots[key];
}

function slotByRun(d: Draft, stageRunId: string): Slot | undefined {
  const key = d.byStageRun[stageRunId];
  return key === undefined ? undefined : slotForWrite(d, key);
}

/**
 * A funnel that ended leaves no stage running: the contract does not promise a stage_failed before
 * funnel_failed, nor a stage_run_id on funnel_stopped.
 */
function endRunningSlots(d: Draft, status: 'failed' | 'stopped', ts: string): void {
  for (const key of d.order) {
    if (d.slots[key]?.status !== 'running') continue;
    const s = slotForWrite(d, key);
    if (!s) continue;
    s.status = status;
    s.eta_s = null;
    s.ended_at = ts;
  }
}

function applyKnown(d: Draft, e: KnownEvent): void {
  switch (e.type) {
    case 'funnel_started': {
      d.header = headerOf(e);
      d.status = 'running';
      d.started_at = e.ts;
      for (const p of e.plan) {
        const key = slotKey(p);
        if (!d.slots[key]) {
          d.slots[key] = emptySlot(p, true);
          d.touched.add(key);
          d.order.push(key);
        }
      }
      break;
    }
    case 'funnel_resumed': {
      d.status = 'running';
      d.failure = null;
      d.finished_at = null;
      d.elapsed_s = null;
      d.resumes += 1;
      if (d.header) d.header = { ...d.header, code_version: e.code_version };
      for (const key of d.order) {
        const s = d.slots[key];
        if (s && (s.status === 'failed' || s.status === 'stopped')) {
          const w = slotForWrite(d, key);
          if (!w) continue;
          if (w.started_at && w.ended_at) {
            w.earlier = [
              ...w.earlier,
              { started_at: w.started_at, ended_at: w.ended_at, status: s.status },
            ];
          }
          Object.assign(w, {
            status: 'queued',
            units_done: 0,
            elapsed_s: null,
            eta_s: null,
            error_kind: null,
            message: null,
            started_at: null,
            ended_at: null,
          } satisfies Partial<Slot>);
        }
      }
      break;
    }
    case 'stage_started': {
      const key = slotKey(e);
      if (!d.slots[key]) {
        d.slots[key] = emptySlot(e, false);
        d.touched.add(key);
        d.order.push(key);
      }
      const s = slotForWrite(d, key);
      if (!s) break;
      if (s.stage_run_id !== null && s.stage_run_id !== e.stage_run_id) {
        const { [s.stage_run_id]: _replaced, ...rest } = d.byStageRun;
        d.byStageRun = rest;
      }
      d.byStageRun[e.stage_run_id] = key;
      if (e.reused && s.status === 'finished') {
        // A resume takes this stage's completed result (D-792): keep its numbers and wall times.
        s.reused = true;
        s.stage_run_id = e.stage_run_id;
        break;
      }
      Object.assign(s, {
        status: 'running',
        reused: e.reused,
        stage_run_id: e.stage_run_id,
        unit_kind: e.unit_kind,
        units_done: 0,
        units_total: e.units_total,
        elapsed_s: 0,
        eta_s: null,
        n_in: null,
        n_passed: null,
        error_kind: null,
        message: null,
        started_at: e.ts,
        ended_at: null,
        attempts: e.reused ? s.attempts : s.attempts + 1,
      } satisfies Partial<Slot>);
      break;
    }
    case 'progress': {
      const s = slotByRun(d, e.stage_run_id);
      if (!s || s.status !== 'running') break;
      s.units_done = e.units_done;
      s.units_total = e.units_total;
      s.elapsed_s = e.elapsed_s;
      s.eta_s = e.eta_s;
      break;
    }
    case 'stage_finished': {
      const s = slotByRun(d, e.stage_run_id);
      if (!s) break;
      if (s.reused && s.status === 'finished') break;
      s.status = 'finished';
      s.elapsed_s = e.elapsed_s;
      s.n_in = e.n_in;
      s.n_passed = e.n_passed;
      if (s.units_total !== null) s.units_done = s.units_total;
      s.eta_s = 0;
      s.ended_at = e.ts;
      break;
    }
    case 'stage_failed': {
      const s = slotByRun(d, e.stage_run_id);
      if (!s) break;
      s.status = 'failed';
      s.elapsed_s = e.elapsed_s;
      s.eta_s = null;
      s.error_kind = e.error_kind;
      s.message = e.message;
      s.ended_at = e.ts;
      break;
    }
    case 'funnel_finished': {
      d.status = 'finished';
      d.elapsed_s = e.elapsed_s;
      d.finished_at = e.ts;
      break;
    }
    case 'funnel_failed': {
      d.status = 'failed';
      d.elapsed_s = e.elapsed_s;
      d.finished_at = e.ts;
      d.failure = { error_kind: e.error_kind, message: e.message };
      endRunningSlots(d, 'failed', e.ts);
      break;
    }
    case 'funnel_stopped': {
      d.status = 'stopped';
      d.elapsed_s = e.elapsed_s;
      d.finished_at = e.ts;
      if (e.stage_run_id !== null) {
        const s = slotByRun(d, e.stage_run_id);
        if (s && s.status === 'running') {
          s.status = 'stopped';
          s.eta_s = null;
          s.ended_at = e.ts;
        }
      }
      endRunningSlots(d, 'stopped', e.ts);
      break;
    }
  }
}

export function applyEvents(state: RunState, events: readonly RunEvent[]): RunState {
  let d: Draft | null = null;
  let dropped = 0;
  for (const e of events) {
    const lastSeq: number = d ? d.lastSeq : state.lastSeq;
    if (e.funnel_run_id !== state.runId || e.seq <= lastSeq) {
      dropped += 1;
      continue;
    }
    if (d === null) {
      d = {
        ...state,
        order: [...state.order],
        slots: { ...state.slots },
        byStageRun: { ...state.byStageRun },
        log: [...state.log],
        touched: new Set<string>(),
      };
    }
    if (e.seq > lastSeq + 1 && lastSeq > 0) d.gaps += 1;
    d.lastSeq = e.seq;
    d.last_ts = e.ts;
    d.applied += 1;
    if (isUnknownEvent(e)) {
      d.log.push(e);
      continue;
    }
    if (e.type !== 'progress') d.log.push(e);
    applyKnown(d, e);
  }
  if (d === null) {
    return dropped === 0
      ? state
      : { ...state, duplicatesDropped: state.duplicatesDropped + dropped };
  }
  const { touched: _touched, ...next } = d;
  next.duplicatesDropped += dropped;
  return next;
}

export function applyEvent(state: RunState, event: RunEvent): RunState {
  return applyEvents(state, [event]);
}

// ---------------------------------------------------------------------------------------------
// Derived views
// ---------------------------------------------------------------------------------------------

export function slotsInOrder(state: RunState): Slot[] {
  return state.order.map((k) => state.slots[k]).filter((s): s is Slot => s !== undefined);
}

export interface RunProgressView {
  total: number;
  done: number;
  running: Slot[];
  queued: number;
  /** The running stages' estimates (null when none is estimable yet); queued stages have none (D-796). */
  remaining_s: number | null;
}

export function progressView(state: RunState): RunProgressView {
  const slots = slotsInOrder(state);
  const running = slots.filter((s) => s.status === 'running');
  const etas = running.map((s) => s.eta_s).filter((x): x is number => x !== null);
  return {
    total: slots.length,
    done: slots.filter((s) => s.status === 'finished').length,
    running,
    queued: slots.filter((s) => s.status === 'queued').length,
    remaining_s: etas.length === 0 ? null : Math.max(...etas),
  };
}
