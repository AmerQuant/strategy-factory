/**
 * The run stream's connection handling (D-782): the first connection carries no id, a reopen carries
 * ?last_event_id=, a drop while running is left to the browser's reconnect, the server closing an
 * ended run stops it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SMOKE_SLOTS } from '../mock/fixtures';
import { SimRun } from '../mock/sim';
import { RunStream } from './runStream';

const RUN_ID = '11111111-2222-4333-8444-555555555555';

class FakeEventSource {
  static last: FakeEventSource | null = null;
  readyState = 0;
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((m: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.last = this;
  }
  deliver(e: { seq: number }) {
    this.onmessage?.({
      data: JSON.stringify(e),
      lastEventId: String(e.seq),
    } as MessageEvent<string>);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
}

function makeRun() {
  return new SimRun(
    {
      funnel_run_id: RUN_ID,
      name: 't',
      config_id: 'funnel_smoke',
      config_hash: 'h',
      code_version: { git_sha: 's', dirty: false },
      source: 'real',
      seed: null,
      control: true,
      slots: SMOKE_SLOTS,
      progress_every_s: 10,
    },
    Date.parse('2026-09-30T10:00:00Z'),
  );
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('T17a-FE run stream', () => {
  it('connects without an id, batches events, reconnects by itself while running', () => {
    const stream = new RunStream(
      RUN_ID,
      (url) => new FakeEventSource(url) as unknown as EventSource,
    );
    stream.ensureOpen();
    const es = FakeEventSource.last;
    if (!es) throw new Error('no source');
    expect(es.url).toBe(`/api/funnel-runs/${RUN_ID}/events`);
    const run = makeRun();
    run.advance(60);
    run.events.forEach((e) => es.deliver(e));
    expect(stream.snapshot.run.lastSeq).toBe(0); // buffered
    vi.advanceTimersByTime(60);
    expect(stream.snapshot.run.lastSeq).toBe(run.lastSeq);

    es.onerror?.(); // network drop: readyState CONNECTING, the browser retries
    expect(stream.snapshot.reconnects).toBe(1);
    expect(stream.snapshot.connection).toBe('connecting');
    expect(es.closed).toBe(false);

    // The reconnect replays from Last-Event-ID; duplicates are dropped by the reducer anyway.
    run.events.slice(-3).forEach((e) => es.deliver(e));
    vi.advanceTimersByTime(60);
    expect(stream.snapshot.run.duplicatesDropped).toBe(3);
  });

  it('stops after the run ended, and a reopen after a resume carries ?last_event_id=', () => {
    const stream = new RunStream(
      RUN_ID,
      (url) => new FakeEventSource(url) as unknown as EventSource,
    );
    stream.ensureOpen();
    const es = FakeEventSource.last;
    if (!es) throw new Error('no source');
    const run = makeRun();
    run.failWhen({ slot: 1, fraction: 0.5, error_kind: 'X', message: 'y' });
    run.advance(1e6);
    run.events.forEach((e) => es.deliver(e));
    es.onerror?.(); // the server closed the stream after funnel_failed
    expect(stream.snapshot.run.status).toBe('failed');
    expect(es.closed).toBe(true);
    expect(stream.snapshot.connection).toBe('closed');

    stream.ensureOpen(); // an ended run is not reopened by itself
    expect(FakeEventSource.last).toBe(es);

    stream.reopen(); // after POST …/resume
    expect(FakeEventSource.last?.url).toBe(
      `/api/funnel-runs/${RUN_ID}/events?last_event_id=${run.lastSeq}`,
    );
  });

  it('reopens with ?last_event_id= when the browser gives up on a running run', () => {
    const stream = new RunStream(
      RUN_ID,
      (url) => new FakeEventSource(url) as unknown as EventSource,
    );
    stream.ensureOpen();
    const es = FakeEventSource.last;
    if (!es) throw new Error('no source');
    const run = makeRun();
    run.advance(60);
    run.events.forEach((e) => es.deliver(e));
    es.readyState = 2; // CLOSED: the browser will not retry
    es.onerror?.();
    expect(stream.snapshot.reconnects).toBe(1);
    expect(FakeEventSource.last).toBe(es);
    vi.advanceTimersByTime(1000);
    expect(FakeEventSource.last).not.toBe(es);
    expect(FakeEventSource.last?.url).toBe(
      `/api/funnel-runs/${RUN_ID}/events?last_event_id=${run.lastSeq}`,
    );
  });

  it('records an event that breaks the contract instead of applying it', () => {
    const stream = new RunStream(
      RUN_ID,
      (url) => new FakeEventSource(url) as unknown as EventSource,
    );
    stream.ensureOpen();
    FakeEventSource.last?.deliver({ seq: 1 });
    expect(stream.snapshot.contractErrors).toHaveLength(1);
    expect(stream.snapshot.run.lastSeq).toBe(0);
  });
});
