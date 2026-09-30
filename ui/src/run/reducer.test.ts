/**
 * The run reducer (T17a-FE §3.1-3.2, D-782, D-791, D-792): order, duplicates, gaps, unknown types and
 * fields, reused stage runs, resume, stop, and a replay of the whole history from every cut point.
 */
import { describe, expect, it } from 'vitest';
import { parseEvent, type RunEvent } from '../api/contract';
import { SMOKE_SLOTS } from '../mock/fixtures';
import { SimRun, type RunSpec } from '../mock/sim';
import {
  applyEvent,
  applyEvents,
  initialRunState,
  progressView,
  slotsInOrder,
  type RunState,
} from './reducer';

const RUN_ID = '11111111-2222-4333-8444-555555555555';

function spec(overrides: Partial<RunSpec> = {}): RunSpec {
  return {
    funnel_run_id: RUN_ID,
    name: 'test',
    config_id: 'funnel_smoke',
    config_hash: 'abc',
    code_version: { git_sha: 'deadbee', dirty: false },
    source: 'planted',
    seed: 3,
    control: true,
    slots: SMOKE_SLOTS,
    progress_every_s: 10,
    ...overrides,
  };
}

const START = Date.parse('2026-09-30T10:00:00Z');

/** Events as the client receives them: JSON over the wire, parsed by the contract. */
function wire(run: SimRun): RunEvent[] {
  return run.events.map((e) => parseEvent(JSON.parse(JSON.stringify(e))));
}

function finishedRun(): RunEvent[] {
  const r = new SimRun(spec(), START);
  r.advance(1e6);
  return wire(r);
}

/** The observable state, without the delivery counters. */
function view(s: RunState) {
  const { applied: _a, duplicatesDropped: _d, ...rest } = s;
  return rest;
}

const fresh = () => initialRunState(RUN_ID);

describe('T17a-FE reducer', () => {
  it('builds every planned stage run from a finished run', () => {
    const s = applyEvents(fresh(), finishedRun());
    expect(s.status).toBe('finished');
    const slots = slotsInOrder(s);
    expect(slots).toHaveLength(SMOKE_SLOTS.length);
    expect(slots.every((x) => x.status === 'finished')).toBe(true);
    expect(slots[0]).toMatchObject({
      stage_id: 's01_edge',
      arm: 'real',
      n_in: 10,
      n_passed: 4,
      units_done: 10,
    });
    expect(s.header).toMatchObject({ source: 'planted', seed: 3, control: true });
    expect(progressView(s)).toMatchObject({ done: 6, total: 6, queued: 0 });
    expect(s.gaps).toBe(0);
  });

  it('gives the same state whether events come one by one or in one batch', () => {
    const events = finishedRun();
    const one = events.reduce(applyEvent, fresh());
    expect(view(one)).toEqual(view(applyEvents(fresh(), events)));
  });

  it('replaying the whole history after a cut at any point neither duplicates nor loses anything', () => {
    const events = finishedRun();
    const once = view(applyEvents(fresh(), events));
    for (let k = 0; k <= events.length; k += 1) {
      const partial = applyEvents(fresh(), events.slice(0, k));
      const replayed = applyEvents(partial, events); // a reconnect without Last-Event-ID
      expect(view(replayed)).toEqual(once);
      expect(replayed.duplicatesDropped).toBe(k);
    }
  });

  it('never moves progress backwards when a reconnect replays older progress events', () => {
    const r = new SimRun(spec(), START);
    r.advance(70); // mid-stage
    const events = wire(r);
    const s = applyEvents(fresh(), events);
    const before = slotsInOrder(s)[0];
    const after = slotsInOrder(applyEvents(s, events.slice(2)))[0];
    expect(after?.units_done).toBe(before?.units_done);
    expect(after?.status).toBe('running');
  });

  it('drops an out-of-order older seq and counts a gap', () => {
    const events = finishedRun();
    const [e1, e2, e3, e4] = events;
    if (!e1 || !e2 || !e3 || !e4) throw new Error('fixture');
    let s = applyEvents(fresh(), [e1, e2, e4]); // e3 missing
    expect(s.gaps).toBe(1);
    s = applyEvent(s, e3); // arrives late: already past it
    expect(s.duplicatesDropped).toBe(1);
    expect(s.lastSeq).toBe(4);
  });

  it('ignores events of another run', () => {
    const [e1] = finishedRun();
    if (!e1) throw new Error('fixture');
    const s = applyEvent(fresh(), { ...e1, funnel_run_id: '99999999-2222-4333-8444-555555555555' });
    expect(s.lastSeq).toBe(0);
  });

  it('keeps an unknown event type in the log and ignores unknown fields', () => {
    const r = new SimRun(spec(), START);
    r.advance(30);
    r.emitRaw({ type: 'checkpoint_written', path: 'x.parquet' });
    r.advance(1e6);
    const raw = JSON.parse(JSON.stringify(r.events)) as Record<string, unknown>[];
    raw[0] = { ...raw[0], field_from_the_future: 42 };
    const events = raw.map(parseEvent);
    const s = applyEvents(fresh(), events);
    const unknown = s.log.filter((e) => e.type === 'checkpoint_written');
    expect(unknown).toHaveLength(1);
    expect(s.status).toBe('finished');
    expect(JSON.stringify(s.log[0])).not.toContain('field_from_the_future');
  });

  it('rejects a malformed known event (contract error)', () => {
    const [e1] = finishedRun();
    expect(() => parseEvent({ ...e1, type: 'progress' })).toThrow();
  });

  it('shows a failure, then a resume with reused stages and the failed attempt kept', () => {
    const r = new SimRun(spec(), START);
    r.failWhen({ slot: 2, fraction: 0.5, error_kind: 'WorkerCrashed', message: 'boom' });
    r.advance(1e6);
    let s = applyEvents(fresh(), wire(r));
    expect(s.status).toBe('failed');
    expect(s.failure?.error_kind).toBe('WorkerCrashed');
    const failed = slotsInOrder(s)[2];
    expect(failed).toMatchObject({
      status: 'failed',
      error_kind: 'WorkerCrashed',
      message: 'boom',
    });
    const firstDone = slotsInOrder(s)[0];

    r.resume(START + 3600_000, { git_sha: 'cafe123', dirty: true });
    r.advance(1e6);
    s = applyEvents(s, wire(r)); // a reopen with ?last_event_id= would send only the new ones
    expect(s.status).toBe('finished');
    expect(s.resumes).toBe(1);
    expect(s.failure).toBeNull();
    expect(s.header?.code_version).toEqual({ git_sha: 'cafe123', dirty: true });
    const slots = slotsInOrder(s);
    expect(slots[0]).toMatchObject({ reused: true, status: 'finished' });
    // The reused stage keeps its original wall times and numbers.
    expect(slots[0]?.started_at).toBe(firstDone?.started_at);
    expect(slots[0]?.ended_at).toBe(firstDone?.ended_at);
    expect(slots[2]).toMatchObject({ reused: false, status: 'finished', attempts: 2 });
    expect(slots[2]?.earlier).toHaveLength(1);
    expect(slots[2]?.earlier[0]?.status).toBe('failed');
  });

  it('marks the interrupted stage when the run is stopped, and re-runs it on resume', () => {
    const r = new SimRun(spec(), START);
    r.advance(150);
    r.stop();
    let s = applyEvents(fresh(), wire(r));
    expect(s.status).toBe('stopped');
    const stopped = slotsInOrder(s).find((x) => x.status === 'stopped');
    expect(stopped).toBeDefined();
    r.resume(START + 60_000, { git_sha: 'x', dirty: false });
    r.advance(1e6);
    s = applyEvents(s, wire(r));
    expect(s.status).toBe('finished');
    const again = s.slots[stopped?.key ?? ''];
    expect(again?.earlier[0]?.status).toBe('stopped');
    expect(again?.reused).toBe(false);
  });

  it('a funnel_failed without stage_failed leaves no stage running, and resume re-queues it clean', () => {
    const r = new SimRun(spec(), START);
    r.advance(70);
    const events = wire(r);
    const last = events[events.length - 1];
    if (!last) throw new Error('fixture');
    const failed = parseEvent({
      schema_version: 1,
      funnel_run_id: RUN_ID,
      seq: last.seq + 1,
      ts: last.ts,
      type: 'funnel_failed',
      elapsed_s: 70,
      error_kind: 'OrchestratorCrashed',
      message: 'x',
    });
    let s = applyEvents(fresh(), [...events, failed]);
    expect(progressView(s).running).toHaveLength(0);
    expect(slotsInOrder(s)[0]?.status).toBe('failed');
    const resumed = parseEvent({
      schema_version: 1,
      funnel_run_id: RUN_ID,
      seq: last.seq + 2,
      ts: last.ts,
      type: 'funnel_resumed',
      code_version: { git_sha: 'x', dirty: false },
    });
    s = applyEvent(s, resumed);
    expect(slotsInOrder(s)[0]).toMatchObject({
      status: 'queued',
      units_done: 0,
      elapsed_s: null,
      error_kind: null,
      started_at: null,
      ended_at: null,
    });
    expect(slotsInOrder(s)[0]?.earlier).toHaveLength(1);
  });

  it('rejects an event of another schema version (contract error)', () => {
    const [e1] = finishedRun();
    expect(() => parseEvent({ ...e1, schema_version: 2 })).toThrow();
  });

  it('reports the current stage estimate as the remaining time; queued stages have none', () => {
    const r = new SimRun(spec(), START);
    r.advance(90);
    const s = applyEvents(fresh(), wire(r));
    const pv = progressView(s);
    expect(pv.running).toHaveLength(1);
    expect(pv.remaining_s).not.toBeNull();
    expect(pv.queued).toBe(SMOKE_SLOTS.length - 1 - pv.done);
  });
});
