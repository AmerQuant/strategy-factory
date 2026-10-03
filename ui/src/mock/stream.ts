/**
 * Mock only: the event-stream logic of `GET /api/funnel-runs/{id}/events` (§3.2), independent of
 * MSW so it is unit-tested in Node (which has no EventSource for MSW's `sse()`).
 *
 * - The `Last-Event-ID` header wins over `?last_event_id=`: on the browser's own reconnect the URL
 *   still carries the id the stream was opened with, the header the newer one.
 * - With neither, the whole history is sent first.
 * - The stream closes after a terminal event, and at once for a run that is no longer running.
 * - A dropped connection is an early end of the stream: the browser's EventSource reconnects by
 *   itself with Last-Event-ID. (MSW's `client.error()` makes Chrome give up instead, which a
 *   network drop does not.)
 */
import { TERMINAL_EVENT_TYPES } from '../api/contract';
import { MockRefusal, type MockBackend } from './backend';
import type { WireEvent } from './sim';

export interface StreamSink {
  retry(ms: number): void;
  send(e: WireEvent): void;
  close(): void;
}

export function parseLastEventId(header: string | null, query: string | null): number {
  for (const v of [header, query]) {
    if (v === null || v === '') continue;
    const n = Number(v);
    if (Number.isInteger(n) && n >= 0) return n;
  }
  return 0;
}

/** Opens a stream; returns the cleanup to call when the client goes away. */
export function openEventStream(
  backend: MockBackend,
  runId: string,
  header: string | null,
  query: string | null,
  sink: StreamSink,
): () => void {
  backend.recordConnection({
    funnel_run_id: runId,
    last_event_id_header: header,
    last_event_id_query: query,
  });
  let history: WireEvent[];
  let run;
  try {
    ({ history, run } = backend.events(runId, parseLastEventId(header, query)));
  } catch (e) {
    if (!(e instanceof MockRefusal)) throw e;
    sink.close();
    return () => undefined;
  }
  sink.retry(500);
  for (const e of history) sink.send(e);
  if (run.status !== 'running') {
    sink.close();
    return () => undefined;
  }
  let done = false;
  const cleanup = () => {
    done = true;
    unsubscribe();
    undrop();
  };
  const unsubscribe = run.subscribe((e) => {
    if (done) return;
    sink.send(e);
    if (TERMINAL_EVENT_TYPES.has(e.type)) {
      cleanup();
      sink.close();
    }
  });
  const undrop = backend.onDrop(() => {
    if (done) return;
    cleanup();
    sink.close();
  });
  return cleanup;
}
