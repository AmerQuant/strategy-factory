/**
 * Mock only: the in-memory backend behind the MSW handlers. It implements T17a-FE §3.3 on top of
 * simulated runs (sim.ts): the history fixtures are replayed at construction, live runs advance on a
 * timer scaled by `speed` (simulated seconds per real second).
 *
 * Refusals are ILLUSTRATIVE of the CLI's (409 / 422 with {error_kind, message}).
 */
import type {
  ApiErrorBody,
  FunnelConfig,
  RunListFilters,
  RunListItem,
  RunSummary,
  ServerStatus,
  StageCount,
  StartRunRequest,
} from '../api/contract';
import { CODE_VERSION, CONFIGS, SERVER_STATUS, slotsFor } from './fixtures';
import { SimRun, type WireEvent } from './sim';

export class MockRefusal extends Error {
  readonly status: 404 | 409 | 422;
  readonly body: ApiErrorBody;
  constructor(status: 404 | 409 | 422, error_kind: string, message: string) {
    super(message);
    this.status = status;
    this.body = { error_kind, message };
  }
}

export interface ConnectionRecord {
  funnel_run_id: string;
  last_event_id_header: string | null;
  last_event_id_query: string | null;
  at_ms: number;
}

export interface MockBackendOptions {
  /** Simulated seconds per real second for live runs. */
  speed?: number;
  /** Build the history fixtures (off in some unit tests). */
  fixtures?: boolean;
  /** Real milliseconds between ticks of the live clock; 0 = no timer (tests advance by hand). */
  tickMs?: number;
  now?: () => number;
  uuid?: () => string;
}

let uuidCounter = 0;
function fallbackUuid(): string {
  uuidCounter += 1;
  const n = uuidCounter.toString(16).padStart(12, '0');
  return `00000000-0000-4000-8000-${n}`;
}

export class MockBackend {
  speed: number;
  readonly runs = new Map<string, SimRun>();
  readonly connections: ConnectionRecord[] = [];
  private readonly now: () => number;
  private readonly uuid: () => string;
  private timer: ReturnType<typeof setInterval> | null = null;
  private dropListeners = new Set<() => void>();
  private failNext = false;

  constructor(opts: MockBackendOptions = {}) {
    this.speed = opts.speed ?? 60;
    this.now = opts.now ?? (() => Date.now());
    this.uuid =
      opts.uuid ??
      (() =>
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : fallbackUuid());
    if (opts.fixtures ?? true) this.buildFixtures();
    const tickMs = opts.tickMs ?? 0;
    if (tickMs > 0) {
      this.timer = setInterval(() => this.advanceLive((tickMs / 1000) * this.speed), tickMs);
    }
  }

  dispose(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  // -------------------------------------------------------------------------------------------
  // Fixtures (D-784)
  // -------------------------------------------------------------------------------------------

  private fixtureRun(
    id: string,
    configId: string,
    name: string,
    source: 'real' | 'null' | 'planted',
    seed: number | null,
    control: boolean,
    startIso: string,
  ): SimRun {
    const cfg = CONFIGS.find((c) => c.config.id === configId);
    if (!cfg) throw new Error(configId);
    const run = new SimRun(
      {
        funnel_run_id: id,
        name,
        config_id: configId,
        config_hash: cfg.config.config_hash,
        code_version: CODE_VERSION,
        source,
        seed,
        control,
        slots: slotsFor(configId, control),
        progress_every_s: 30,
      },
      Date.parse(startIso),
    );
    this.runs.set(id, run);
    return run;
  }

  private buildFixtures(): void {
    // 1. The planted funnel with T15a's real timings.
    const planted = this.fixtureRun(
      '5b1e8f0a-3c47-4d2e-9a61-7f2c0d8e4b11',
      'funnel_planted_pilot',
      'T15a planted pilot',
      'planted',
      20260929,
      true,
      '2026-09-29T19:04:00Z',
    );
    planted.advance(1e6);

    // 2. A failed-and-resumed run on the calibrated null.
    const resumed = this.fixtureRun(
      'a3d9c6e2-8b14-4f70-b5d3-2e6a9c1f0d42',
      'funnel_default',
      'Null seed 7 (resumed)',
      'null',
      7,
      true,
      '2026-09-28T21:10:00Z',
    );
    resumed.failWhen({
      slot: 6,
      fraction: 0.62,
      error_kind: 'WorkerCrashed',
      message: 'worker 3 exited with code 137 (out of memory) while evaluating profile 301 of 486',
    });
    resumed.advance(1e6);
    resumed.resume(Date.parse('2026-09-29T07:45:00Z'), { git_sha: '7617337', dirty: false });
    resumed.advance(1e6);

    // 3. A real-data run with the control off (D-653 flagged).
    const noControl = this.fixtureRun(
      'c81f4a07-6e25-4b9c-8d30-51a7e2f96c03',
      'funnel_default',
      'Real, no control',
      'real',
      null,
      false,
      '2026-09-27T14:30:00Z',
    );
    noControl.advance(1e6);

    // 4. A run whose stream contains an event type this UI does not know (forward compatibility).
    const unknown = this.fixtureRun(
      'e4b27d19-0f6c-4a83-9e5b-c3d1a8f27e64',
      'funnel_smoke',
      'Smoke with a future event',
      'planted',
      11,
      true,
      '2026-09-26T09:00:00Z',
    );
    unknown.advance(150);
    unknown.emitRaw({
      type: 'checkpoint_written',
      path: 'artifacts/checkpoints/s01.parquet',
      bytes: 81234,
    });
    unknown.advance(1e6);

    // 5. A stopped run.
    const stopped = this.fixtureRun(
      'f6a0b3c8-2d59-4e17-a4f2-9b8e7c6d5a10',
      'funnel_default',
      'Real, stopped by the user',
      'real',
      null,
      true,
      '2026-09-25T10:00:00Z',
    );
    stopped.advance(40 * 60);
    stopped.stop();
  }

  // -------------------------------------------------------------------------------------------
  // Live clock and test controls
  // -------------------------------------------------------------------------------------------

  /** Advances every running run by `dt` simulated seconds. */
  advanceLive(dt: number): void {
    for (const run of this.runs.values()) {
      if (run.status === 'running') run.advance(dt);
    }
  }

  /** Drops every open event stream (the client's EventSource reconnects by itself). */
  dropConnections(): void {
    for (const fn of [...this.dropListeners]) fn();
  }

  onDrop(fn: () => void): () => void {
    this.dropListeners.add(fn);
    return () => this.dropListeners.delete(fn);
  }

  /** The next running stage (of any run) fails halfway. */
  failNextStage(): void {
    this.failNext = true;
    for (const run of this.runs.values()) {
      if (run.status === 'running') {
        run.failWhen({
          fraction: 0.5,
          error_kind: 'InjectedFailure',
          message: 'failure injected by the mock',
        });
        this.failNext = false;
      }
    }
  }

  recordConnection(rec: Omit<ConnectionRecord, 'at_ms'>): void {
    this.connections.push({ ...rec, at_ms: this.now() });
  }

  // -------------------------------------------------------------------------------------------
  // §3.3
  // -------------------------------------------------------------------------------------------

  private get(id: string): SimRun {
    const run = this.runs.get(id);
    if (!run) throw new MockRefusal(404, 'not_found', `no funnel run ${id}`);
    return run;
  }

  summary(id: string): RunSummary {
    const run = this.get(id);
    const started = run.events[0];
    if (!started || started.type !== 'funnel_started') throw new Error('bad run');
    const s = run.spec;
    return {
      funnel_run_id: s.funnel_run_id,
      name: s.name,
      config_id: s.config_id,
      config_hash: s.config_hash,
      profile_hash: null,
      code_version: s.code_version,
      source: s.source,
      seed: s.seed,
      control: s.control,
      plan: s.slots.map(({ stage_id, timeframe, arm }) => ({ stage_id, timeframe, arm })),
      status: run.status,
      started_at: new Date(run.startedAtMs).toISOString(),
      finished_at: run.finishedAtMs === null ? null : new Date(run.finishedAtMs).toISOString(),
      elapsed_s: Math.round(run.activeS * 10) / 10,
      stage_runs: run.stageRuns.map((r) => ({ ...r })),
    };
  }

  private listItem(id: string): RunListItem {
    const { stage_runs, ...rest } = this.summary(id);
    const byStage = new Map<string, StageCount>();
    for (const stage of new Set(rest.plan.map((p) => p.stage_id))) {
      byStage.set(stage, { stage_id: stage, real: null, control: null });
    }
    for (const r of stage_runs) {
      const c = byStage.get(r.stage_id);
      if (!c || r.status !== 'finished' || r.n_passed === null) continue;
      c[r.arm] = (c[r.arm] ?? 0) + r.n_passed;
    }
    return { ...rest, stage_counts: [...byStage.values()] };
  }

  list(filters: RunListFilters = {}): RunListItem[] {
    return [...this.runs.keys()]
      .map((id) => this.listItem(id))
      .filter((r) => !filters.source || r.source === filters.source)
      .filter((r) => !filters.status || r.status === filters.status)
      .filter((r) => !filters.started_from || (r.started_at ?? '') >= filters.started_from)
      .filter((r) => !filters.started_to || (r.started_at ?? '').slice(0, 10) <= filters.started_to)
      .sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''));
  }

  configs(): FunnelConfig[] {
    return CONFIGS.map((c) => c.config);
  }

  status(): ServerStatus {
    return SERVER_STATUS;
  }

  start(req: StartRunRequest): { funnel_run_id: string } {
    const cfg = CONFIGS.find((c) => c.config.id === req.config);
    if (!cfg) throw new MockRefusal(422, 'unknown_config', `unknown funnel config '${req.config}'`);
    if (req.source !== 'real' && req.seed === null) {
      throw new MockRefusal(422, 'seed_required', `source '${req.source}' needs --seed`);
    }
    if (req.source === 'planted' && cfg.config.planted_ladder === null) {
      throw new MockRefusal(
        422,
        'no_planted_ladder',
        `config '${req.config}' has no planted ladder; --source planted needs one`,
      );
    }
    const busy = [...this.runs.values()].find((r) => r.status === 'running');
    if (busy) {
      throw new MockRefusal(
        409,
        'run_in_progress',
        `funnel run ${busy.spec.funnel_run_id} is still running; one funnel run at a time`,
      );
    }
    const id = this.uuid();
    const run = new SimRun(
      {
        funnel_run_id: id,
        name: `${cfg.config.id} ${req.source}${req.seed === null ? '' : ` seed ${req.seed}`}`,
        config_id: cfg.config.id,
        config_hash: cfg.config.config_hash,
        code_version: { ...CODE_VERSION, dirty: true },
        source: req.source,
        seed: req.seed,
        control: req.control,
        slots: slotsFor(cfg.config.id, req.control),
        progress_every_s: 1,
      },
      this.now(),
    );
    if (this.failNext) {
      run.failWhen({
        fraction: 0.5,
        error_kind: 'InjectedFailure',
        message: 'failure injected by the mock',
      });
      this.failNext = false;
    }
    this.runs.set(id, run);
    return { funnel_run_id: id };
  }

  resume(id: string): { funnel_run_id: string } {
    const run = this.get(id);
    if (run.status !== 'failed' && run.status !== 'stopped') {
      throw new MockRefusal(
        409,
        'not_resumable',
        `funnel run ${id} is ${run.status}; only a failed or stopped run can be resumed`,
      );
    }
    const busy = [...this.runs.values()].find((r) => r.status === 'running');
    if (busy) {
      throw new MockRefusal(
        409,
        'run_in_progress',
        `funnel run ${busy.spec.funnel_run_id} is still running`,
      );
    }
    run.resume(this.now(), { ...CODE_VERSION, dirty: true });
    return { funnel_run_id: id };
  }

  stop(id: string): { funnel_run_id: string } {
    const run = this.get(id);
    if (run.status !== 'running') {
      throw new MockRefusal(
        409,
        'not_running',
        `funnel run ${id} is ${run.status}; only a running run can be stopped`,
      );
    }
    run.stop();
    return { funnel_run_id: id };
  }

  /** Events after `afterSeq` (the whole history for 0), and a subscription to the new ones. */
  events(id: string, afterSeq: number): { history: WireEvent[]; run: SimRun } {
    const run = this.get(id);
    return { history: run.events.filter((e) => e.seq > afterSeq), run };
  }
}
