/**
 * The mock API (T17a-FE §2, §3.2-3.3): every fixture event and response matches the contract; the
 * event stream honours Last-Event-ID and ?last_event_id=; start, stop and resume; the refusals; the
 * T15a timings (D-784).
 */
import { afterEach, describe, expect, it } from 'vitest';
import {
  FunnelConfigListSchema,
  parseEvent,
  RunListSchema,
  RunSummarySchema,
  ServerStatusSchema,
} from '../api/contract';
import { MockBackend, MockRefusal } from './backend';
import { PLANTED_PILOT_SLOTS } from './fixtures';
import type { WireEvent } from './sim';
import { openEventStream, parseLastEventId, type StreamSink } from './stream';

const PLANTED = '5b1e8f0a-3c47-4d2e-9a61-7f2c0d8e4b11';

function sink() {
  const s = { sent: [] as WireEvent[], closed: false, retry: 0 };
  const api: StreamSink = {
    retry: (ms) => (s.retry = ms),
    send: (e) => s.sent.push(e),
    close: () => (s.closed = true),
  };
  return { s, api };
}

let backend: MockBackend;
afterEach(() => backend?.dispose());

function refusalOf(fn: () => unknown): MockRefusal {
  try {
    fn();
  } catch (e) {
    if (e instanceof MockRefusal) return e;
    throw e;
  }
  throw new Error('not refused');
}

describe('T17a-FE mock: contract conformance', () => {
  it('every fixture event parses with the contract; unknown types only in the forward-compatibility run', () => {
    backend = new MockBackend();
    for (const run of backend.runs.values()) {
      let seq = 0;
      for (const e of run.events) {
        const parsed = parseEvent(JSON.parse(JSON.stringify(e)));
        expect(parsed.seq).toBe(++seq);
        if ('unknown' in parsed) expect(run.spec.name).toBe('Smoke with a future event');
      }
    }
  });

  it('list, summary, configs and status match the contract', () => {
    backend = new MockBackend();
    expect(() => RunListSchema.parse(backend.list())).not.toThrow();
    for (const id of backend.runs.keys())
      expect(() => RunSummarySchema.parse(backend.summary(id))).not.toThrow();
    expect(() => FunnelConfigListSchema.parse(backend.configs())).not.toThrow();
    expect(() => ServerStatusSchema.parse(backend.status())).not.toThrow();
  });

  it('the fixtures cover T15a, failed-and-resumed, control off and stopped', () => {
    backend = new MockBackend();
    const runs = backend.list();
    expect(runs.find((r) => r.name === 'T15a planted pilot')?.status).toBe('finished');
    const resumed = backend.runs.get('a3d9c6e2-8b14-4f70-b5d3-2e6a9c1f0d42');
    expect(resumed?.events.some((e) => e.type === 'stage_failed')).toBe(true);
    expect(resumed?.events.some((e) => e.type === 'funnel_resumed')).toBe(true);
    expect(resumed?.status).toBe('finished');
    expect(runs.find((r) => !r.control)?.stage_counts.every((c) => c.control === null)).toBe(true);
    expect(runs.some((r) => r.status === 'stopped')).toBe(true);
  });

  it("uses T15a's real timings for the planted funnel (D-784)", () => {
    const minutes = (stage: string, tf: string, arm: string) =>
      (PLANTED_PILOT_SLOTS.find((s) => s.stage_id === stage && s.timeframe === tf && s.arm === arm)
        ?.duration_s ?? 0) / 60;
    expect([minutes('s01_edge', '1D', 'real'), minutes('s01_edge', '1D', 'control')]).toEqual([
      13, 12,
    ]);
    expect([minutes('s02_screen', '1D', 'real'), minutes('s02_screen', '1D', 'control')]).toEqual([
      15, 16,
    ]);
    expect([minutes('s03_entry', '1D', 'real'), minutes('s03_entry', '1D', 'control')]).toEqual([
      7, 7,
    ]);
    expect([minutes('s01_edge', '1H', 'real'), minutes('s01_edge', '1H', 'control')]).toEqual([
      29, 27,
    ]);
    expect(minutes('s02_screen', '1H', 'real')).toBe(6);
    backend = new MockBackend();
    const planted = backend.summary(PLANTED);
    expect(planted.stage_runs.map((r) => r.elapsed_s)).toEqual(
      PLANTED_PILOT_SLOTS.map((s) => s.duration_s),
    );
  });
});

describe('T17a-FE mock: event stream (§3.2)', () => {
  it('with neither header nor query sends the whole history, then closes for an ended run', () => {
    backend = new MockBackend();
    const { s, api } = sink();
    openEventStream(backend, PLANTED, null, null, api);
    expect(s.sent.map((e) => e.seq)).toEqual(backend.runs.get(PLANTED)?.events.map((e) => e.seq));
    expect(s.closed).toBe(true);
    expect(s.retry).toBeGreaterThan(0);
  });

  it('resumes after ?last_event_id=, and the Last-Event-ID header wins over the query', () => {
    backend = new MockBackend();
    const q = sink();
    openEventStream(backend, PLANTED, null, '100', q.api);
    expect(q.s.sent[0]?.seq).toBe(101);
    const h = sink();
    openEventStream(backend, PLANTED, '200', '100', h.api);
    expect(h.s.sent[0]?.seq).toBe(201);
    expect(parseLastEventId('', 'x')).toBe(0);
    expect(backend.connections.map((c) => [c.last_event_id_header, c.last_event_id_query])).toEqual(
      [
        [null, '100'],
        ['200', '100'],
      ],
    );
  });

  it('streams a live run, survives a drop without duplicating or losing events, and ends at the terminal event', () => {
    backend = new MockBackend({ fixtures: false });
    const { funnel_run_id: id } = backend.start({
      config: 'funnel_smoke',
      source: 'null',
      seed: 1,
      control: true,
    });
    const a = sink();
    openEventStream(backend, id, null, null, a.api);
    backend.advanceLive(90); // mid-stage
    backend.dropConnections();
    expect(a.s.closed).toBe(true);
    const lastSeen = a.s.sent[a.s.sent.length - 1]?.seq ?? 0;
    backend.advanceLive(30); // events produced while disconnected
    const b = sink();
    openEventStream(backend, id, String(lastSeen), '0', b.api); // the browser's reconnect
    backend.advanceLive(1e6);
    const seqs = [...a.s.sent, ...b.s.sent].map((e) => e.seq);
    expect(seqs).toEqual(backend.runs.get(id)?.events.map((e) => e.seq));
    expect(b.s.sent[b.s.sent.length - 1]?.type).toBe('funnel_finished');
    expect(b.s.closed).toBe(true);
  });

  it('closes on an unknown run', () => {
    backend = new MockBackend({ fixtures: false });
    const { s, api } = sink();
    openEventStream(backend, 'nope', null, null, api);
    expect(s.closed).toBe(true);
    expect(s.sent).toHaveLength(0);
  });
});

describe('T17a-FE mock: start, stop, resume and refusals (§3.3)', () => {
  it('stop ends a running run with funnel_stopped; resume keeps the id and reuses the finished stages', () => {
    backend = new MockBackend({ fixtures: false });
    const { funnel_run_id: id } = backend.start({
      config: 'funnel_smoke',
      source: 'real',
      seed: null,
      control: true,
    });
    backend.advanceLive(200);
    expect(backend.stop(id)).toEqual({ funnel_run_id: id });
    const run = backend.runs.get(id);
    expect(run?.events[run.events.length - 1]?.type).toBe('funnel_stopped');
    expect(backend.resume(id)).toEqual({ funnel_run_id: id });
    const resumed = run?.events.find((e) => e.type === 'funnel_resumed');
    expect(resumed).toBeDefined();
    const reused = run?.events.filter((e) => e.type === 'stage_started' && e.reused === true);
    expect(reused?.length).toBeGreaterThan(0);
    backend.advanceLive(1e6);
    expect(backend.summary(id).status).toBe('finished');
  });

  it('refuses what the CLI would refuse, with {error_kind, message}', () => {
    backend = new MockBackend({ fixtures: false });
    expect(
      refusalOf(() => backend.start({ config: 'x', source: 'real', seed: null, control: true }))
        .status,
    ).toBe(422);
    expect(
      refusalOf(() =>
        backend.start({ config: 'funnel_smoke', source: 'null', seed: null, control: true }),
      ).body.error_kind,
    ).toBe('seed_required');
    expect(
      refusalOf(() =>
        backend.start({ config: 'funnel_default', source: 'planted', seed: 1, control: true }),
      ).body.error_kind,
    ).toBe('no_planted_ladder');
    const { funnel_run_id: id } = backend.start({
      config: 'funnel_smoke',
      source: 'real',
      seed: null,
      control: true,
    });
    expect(
      refusalOf(() =>
        backend.start({ config: 'funnel_smoke', source: 'real', seed: null, control: true }),
      ).status,
    ).toBe(409);
    expect(refusalOf(() => backend.resume(id)).body.error_kind).toBe('not_resumable');
    backend.stop(id);
    expect(refusalOf(() => backend.stop(id)).body.error_kind).toBe('not_running');
    expect(refusalOf(() => backend.summary('nope')).status).toBe(404);
  });

  it('the control off leaves the control arm out of the plan', () => {
    backend = new MockBackend({ fixtures: false });
    const { funnel_run_id: id } = backend.start({
      config: 'funnel_smoke',
      source: 'real',
      seed: null,
      control: false,
    });
    expect(backend.summary(id).plan.every((p) => p.arm === 'real')).toBe(true);
  });

  it('filters the list by source, status and start date', () => {
    backend = new MockBackend();
    expect(backend.list({ source: 'null' }).map((r) => r.source)).toEqual(['null']);
    expect(backend.list({ status: 'stopped' })).toHaveLength(1);
    expect(
      backend.list({ started_from: '2026-09-28', started_to: '2026-09-28' }).map((r) => r.name),
    ).toEqual(['Null seed 7 (resumed)']);
  });

  it('counts passes per stage id, real against control', () => {
    backend = new MockBackend();
    const planted = backend.list().find((r) => r.funnel_run_id === PLANTED);
    expect(planted?.stage_counts).toEqual([
      { stage_id: 's01_edge', real: 41 + 33, control: 0 },
      { stage_id: 's02_screen', real: 23 + 17, control: 0 },
      { stage_id: 's03_entry', real: 9 + 5, control: 0 },
    ]);
  });
});
