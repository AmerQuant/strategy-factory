/**
 * Mock only (dev and tests, never in a production build): one simulated funnel run.
 *
 * Produces the contract's events (§3.1) on a simulated clock. Stage runs execute one after another
 * in plan order. `advance(dt)` moves the clock by `dt` simulated seconds; the fixtures replay whole
 * runs with it, the live mock calls it from a timer scaled by a speed factor.
 */
import type {
  Arm,
  CodeVersion,
  KnownEvent,
  RunStatus,
  Source,
  StageRunSummary,
  Timeframe,
} from '../api/contract';

export interface SlotSpec {
  stage_id: string;
  timeframe: Timeframe;
  arm: Arm;
  duration_s: number;
  units_total: number;
  unit_kind: string;
  n_in: number;
  n_passed: number;
}

export interface RunSpec {
  funnel_run_id: string;
  name: string;
  config_id: string;
  config_hash: string;
  code_version: CodeVersion;
  source: Source;
  seed: number | null;
  control: boolean;
  slots: SlotSpec[];
  /** Emit a progress event at most every this many simulated seconds (the producer's throttle, >= 1). */
  progress_every_s: number;
}

type EventBody = Record<string, unknown> & { type: string };
/** A wire event: a known event or, for the forward-compatibility fixture, an unknown type. */
export type WireEvent = KnownEvent | (EventBody & Omit<KnownEvent, 'type'>);

/** A stage run the simulation has started: it always has an id (queued ones have none, D-794). */
type StartedStageRun = StageRunSummary & { stage_run_id: string };

export interface PendingFailure {
  /** Fail when the current stage reaches this fraction. */
  fraction: number;
  error_kind: string;
  message: string;
  /** Only in this slot (plan index); any slot when undefined. */
  slot?: number;
}

export class SimRun {
  readonly spec: RunSpec;
  readonly events: WireEvent[] = [];
  status: RunStatus = 'running';
  startedAtMs: number;
  finishedAtMs: number | null = null;
  /** Active (simulated) seconds across all attempts. */
  activeS = 0;

  private seq = 0;
  private tsBaseMs: number;
  private tsBaseActive = 0;
  private cursor = 0;
  private slotElapsed = 0;
  private sinceProgress = 0;
  private attempts: number[];
  private runs: (StartedStageRun | null)[];
  private failure: PendingFailure | null = null;
  private listeners = new Set<(e: WireEvent) => void>();

  constructor(spec: RunSpec, startMs: number) {
    this.spec = spec;
    this.startedAtMs = startMs;
    this.tsBaseMs = startMs;
    this.attempts = spec.slots.map(() => 0);
    this.runs = spec.slots.map(() => null);
    this.emit({
      type: 'funnel_started',
      name: spec.name,
      config_id: spec.config_id,
      config_hash: spec.config_hash,
      profile_hash: null,
      code_version: spec.code_version,
      source: spec.source,
      seed: spec.seed,
      control: spec.control,
      plan: spec.slots.map(({ stage_id, timeframe, arm }) => ({ stage_id, timeframe, arm })),
    });
    this.startSlot();
  }

  get lastSeq(): number {
    return this.seq;
  }

  get stageRuns(): StageRunSummary[] {
    return this.runs.filter((r): r is StartedStageRun => r !== null);
  }

  get currentStageRunId(): string | null {
    return this.status === 'running' ? (this.runs[this.cursor]?.stage_run_id ?? null) : null;
  }

  subscribe(fn: (e: WireEvent) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  failWhen(f: PendingFailure): void {
    this.failure = f;
  }

  private nowIso(): string {
    return new Date(this.tsBaseMs + (this.activeS - this.tsBaseActive) * 1000).toISOString();
  }

  private emit(body: EventBody): WireEvent {
    this.seq += 1;
    const e = {
      schema_version: 1,
      funnel_run_id: this.spec.funnel_run_id,
      seq: this.seq,
      ts: this.nowIso(),
      ...body,
    } as WireEvent;
    this.events.push(e);
    for (const fn of this.listeners) fn(e);
    return e;
  }

  /** Emits a raw event (the fixture with an unknown `type`). */
  emitRaw(body: EventBody): void {
    this.emit(body);
  }

  private stageRunId(i: number): string {
    const s = this.spec.slots[i];
    if (!s) throw new Error(`no slot ${i}`);
    const short = this.spec.funnel_run_id.slice(0, 8);
    return `${short}-${s.stage_id}-${s.timeframe}-${s.arm}-a${this.attempts[i]}`;
  }

  private startSlot(): void {
    const s = this.spec.slots[this.cursor];
    if (!s) {
      this.finishFunnel();
      return;
    }
    this.attempts[this.cursor] = (this.attempts[this.cursor] ?? 0) + 1;
    const id = this.stageRunId(this.cursor);
    this.slotElapsed = 0;
    this.sinceProgress = 0;
    this.runs[this.cursor] = {
      stage_id: s.stage_id,
      timeframe: s.timeframe,
      arm: s.arm,
      stage_run_id: id,
      status: 'running',
      reused: false,
      elapsed_s: null,
      n_in: null,
      n_passed: null,
    };
    this.emit({
      type: 'stage_started',
      stage_id: s.stage_id,
      timeframe: s.timeframe,
      arm: s.arm,
      stage_run_id: id,
      units_total: s.units_total,
      unit_kind: s.unit_kind,
      reused: false,
    });
  }

  private finishFunnel(): void {
    this.status = 'finished';
    this.emit({ type: 'funnel_finished', elapsed_s: round(this.activeS) });
    this.finishedAtMs = Date.parse(this.nowIso());
  }

  private emitProgress(s: SlotSpec, id: string): void {
    const frac = Math.min(1, this.slotElapsed / s.duration_s);
    const done = Math.floor(s.units_total * frac);
    const eta =
      done === 0 || frac < 0.05 ? null : (this.slotElapsed * (s.units_total - done)) / done;
    this.emit({
      type: 'progress',
      stage_run_id: id,
      units_done: done,
      units_total: s.units_total,
      elapsed_s: round(this.slotElapsed),
      eta_s: eta === null ? null : round(eta),
    });
  }

  /** Moves the simulated clock by `dt` seconds. */
  advance(dt: number): void {
    let left = dt;
    while (left > 0 && this.status === 'running') {
      const s = this.spec.slots[this.cursor];
      const run = this.runs[this.cursor];
      if (!s || !run) return;
      const f = this.failure;
      const failHere = f !== null && (f.slot === undefined || f.slot === this.cursor);
      const failAt = failHere ? f.fraction * s.duration_s : Infinity;
      const nextProgress = this.spec.progress_every_s - this.sinceProgress;
      const toEnd = Math.min(s.duration_s, failAt) - this.slotElapsed;
      const step = Math.max(0, Math.min(left, nextProgress, toEnd));
      this.slotElapsed += step;
      this.sinceProgress += step;
      this.activeS += step;
      left -= step;
      if (failHere && this.slotElapsed >= failAt && f) {
        this.failure = null;
        run.status = 'failed';
        run.elapsed_s = round(this.slotElapsed);
        this.emit({
          type: 'stage_failed',
          stage_run_id: run.stage_run_id,
          elapsed_s: round(this.slotElapsed),
          error_kind: f.error_kind,
          message: f.message,
        });
        this.status = 'failed';
        this.emit({
          type: 'funnel_failed',
          elapsed_s: round(this.activeS),
          error_kind: f.error_kind,
          message: `stage ${s.stage_id} ${s.timeframe} ${s.arm} failed: ${f.message}`,
        });
        this.finishedAtMs = Date.parse(this.nowIso());
        return;
      }
      if (this.slotElapsed >= s.duration_s) {
        run.status = 'finished';
        run.elapsed_s = round(s.duration_s);
        run.n_in = s.n_in;
        run.n_passed = s.n_passed;
        this.emit({
          type: 'stage_finished',
          stage_run_id: run.stage_run_id,
          elapsed_s: round(s.duration_s),
          n_in: s.n_in,
          n_passed: s.n_passed,
        });
        this.cursor += 1;
        this.startSlot();
        continue;
      }
      if (this.sinceProgress >= this.spec.progress_every_s) {
        this.sinceProgress = 0;
        this.emitProgress(s, run.stage_run_id);
      }
    }
  }

  stop(): void {
    if (this.status !== 'running') return;
    const run = this.runs[this.cursor];
    if (run) {
      run.status = 'stopped';
      run.elapsed_s = round(this.slotElapsed);
    }
    this.status = 'stopped';
    this.emit({
      type: 'funnel_stopped',
      elapsed_s: round(this.activeS),
      stage_run_id: run?.stage_run_id ?? null,
    });
    this.finishedAtMs = Date.parse(this.nowIso());
  }

  /** Resumes a failed or stopped run at wall time `atMs`: completed stages are reused (D-783). */
  resume(atMs: number, codeVersion: CodeVersion): void {
    if (this.status !== 'failed' && this.status !== 'stopped') return;
    this.tsBaseMs = atMs;
    this.tsBaseActive = this.activeS;
    this.status = 'running';
    this.finishedAtMs = null;
    this.emit({ type: 'funnel_resumed', code_version: codeVersion });
    let first = -1;
    this.spec.slots.forEach((s, i) => {
      const run = this.runs[i];
      if (run && run.status === 'finished') {
        run.reused = true;
        this.emit({
          type: 'stage_started',
          stage_id: s.stage_id,
          timeframe: s.timeframe,
          arm: s.arm,
          stage_run_id: run.stage_run_id,
          units_total: s.units_total,
          unit_kind: s.unit_kind,
          reused: true,
        });
        this.emit({
          type: 'stage_finished',
          stage_run_id: run.stage_run_id,
          elapsed_s: run.elapsed_s ?? 0,
          n_in: run.n_in ?? 0,
          n_passed: run.n_passed ?? 0,
        });
      } else if (first < 0) {
        first = i;
      }
    });
    this.cursor = first < 0 ? this.spec.slots.length : first;
    this.startSlot();
  }
}

function round(x: number): number {
  return Math.round(x * 10) / 10;
}
