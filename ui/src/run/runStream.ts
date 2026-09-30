/**
 * The live connection to one run's events (D-782): the browser's EventSource, whose own reconnect
 * sends `Last-Event-ID`; a fresh connection passes the last applied seq as `?last_event_id=`; the
 * reducer drops any seq it has already applied.
 *
 * One store per run id, kept while the app is open, so leaving the monitor and coming back resumes
 * from the last applied event instead of replaying the history.
 */
import { useEffect, useSyncExternalStore } from 'react';
import { eventsUrl } from '../api/client';
import { parseEvent, type RunEvent } from '../api/contract';
import { applyEvents, initialRunState, type RunState } from './reducer';

export type ConnectionState = 'idle' | 'connecting' | 'open' | 'closed';

export interface RunStreamSnapshot {
  run: RunState;
  connection: ConnectionState;
  /** Times the connection dropped and the browser reconnected. */
  reconnects: number;
  /** Events that did not match the contract (not applied). */
  contractErrors: string[];
}

const TERMINAL = new Set(['finished', 'failed', 'stopped']);
const FLUSH_MS = 50;
/** When the browser gives up on a run that has not ended, reopen after this long. */
const REOPEN_MS = 1000;

export type EventSourceFactory = (url: string) => EventSource;

export class RunStream {
  private snap: RunStreamSnapshot;
  private es: EventSource | null = null;
  private buffer: RunEvent[] = [];
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private reopenTimer: ReturnType<typeof setTimeout> | null = null;
  private listeners = new Set<() => void>();
  private readonly factory: EventSourceFactory;

  constructor(runId: string, factory: EventSourceFactory = (url) => new EventSource(url)) {
    this.factory = factory;
    this.snap = {
      run: initialRunState(runId),
      connection: 'idle',
      reconnects: 0,
      contractErrors: [],
    };
  }

  get snapshot(): RunStreamSnapshot {
    return this.snap;
  }

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  getSnapshot = (): RunStreamSnapshot => this.snap;

  private set(patch: Partial<RunStreamSnapshot>): void {
    this.snap = { ...this.snap, ...patch };
    for (const fn of this.listeners) fn();
  }

  private flush = (): void => {
    if (this.flushTimer !== null) clearTimeout(this.flushTimer);
    this.flushTimer = null;
    if (this.buffer.length === 0) return;
    const batch = this.buffer;
    this.buffer = [];
    this.set({ run: applyEvents(this.snap.run, batch) });
  };

  /** Opens the stream unless it is open or the run is known to have ended. */
  ensureOpen(): void {
    if (this.es !== null) return;
    if (this.snap.run.lastSeq > 0 && TERMINAL.has(this.snap.run.status)) return;
    this.open();
  }

  /** Closes and opens again from the last applied seq (after a resume). */
  reopen(): void {
    this.close();
    this.open();
  }

  private open(): void {
    const es = this.factory(eventsUrl(this.snap.run.runId, this.snap.run.lastSeq));
    this.es = es;
    this.set({ connection: 'connecting' });
    es.onopen = () => {
      if (this.es === es) this.set({ connection: 'open' });
    };
    es.onmessage = (msg: MessageEvent<string>) => {
      if (this.es !== es) return;
      try {
        this.buffer.push(parseEvent(JSON.parse(msg.data)));
      } catch (err) {
        this.set({
          contractErrors: [...this.snap.contractErrors, `event ${msg.lastEventId}: ${String(err)}`],
        });
        return;
      }
      if (this.flushTimer === null) this.flushTimer = setTimeout(this.flush, FLUSH_MS);
    };
    es.onerror = () => {
      if (this.es !== es) return;
      this.flush();
      // The server closes the stream after the run's last event: then stop, do not reconnect.
      if (TERMINAL.has(this.snap.run.status)) {
        es.close();
        this.es = null;
        this.set({ connection: 'closed' });
        return;
      }
      this.set({ connection: 'connecting', reconnects: this.snap.reconnects + 1 });
      // The browser gave up (a fatal error): reopen from the last applied seq ourselves.
      if (es.readyState === 2 /* CLOSED */) {
        this.es = null;
        this.reopenTimer = setTimeout(() => {
          this.reopenTimer = null;
          if (this.es === null) this.open();
        }, REOPEN_MS);
      }
    };
  }

  close(): void {
    if (this.reopenTimer !== null) clearTimeout(this.reopenTimer);
    this.reopenTimer = null;
    this.flush();
    if (this.es) this.es.close();
    this.es = null;
    if (this.snap.connection !== 'closed') this.set({ connection: 'closed' });
  }

  get isOpen(): boolean {
    return this.es !== null;
  }
}

const streams = new Map<string, RunStream>();

export function getRunStream(runId: string): RunStream {
  let s = streams.get(runId);
  if (!s) {
    s = new RunStream(runId);
    streams.set(runId, s);
  }
  return s;
}

/** The live state of a run; opens its stream while mounted. */
export function useRunStream(runId: string): { stream: RunStream; snapshot: RunStreamSnapshot } {
  const stream = getRunStream(runId);
  const snapshot = useSyncExternalStore(stream.subscribe, stream.getSnapshot);
  useEffect(() => {
    stream.ensureOpen();
    return () => stream.close();
  }, [stream]);
  return { stream, snapshot };
}
