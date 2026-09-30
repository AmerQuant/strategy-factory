/**
 * Mock only: the MSW handlers of §3.3 over a MockBackend. `sse()` needs EventSource, so the event
 * stream handler is added only where it exists (the browser).
 */
import { http, HttpResponse, sse, type RequestHandler } from 'msw';
import {
  RunStatusSchema,
  SourceSchema,
  StartRunRequestSchema,
  type RunListFilters,
} from '../api/contract';
import { MockRefusal, type MockBackend } from './backend';
import { openEventStream } from './stream';

function refusal(e: unknown): Response {
  if (e instanceof MockRefusal) return HttpResponse.json(e.body, { status: e.status });
  throw e;
}

function guard(fn: () => unknown): Response {
  try {
    return HttpResponse.json(fn() as never);
  } catch (e) {
    return refusal(e);
  }
}

export function httpHandlers(backend: MockBackend): RequestHandler[] {
  return [
    http.get('/api/status', () => guard(() => backend.status())),
    http.get('/api/configs', () => guard(() => backend.configs())),
    http.get('/api/funnel-runs', ({ request }) => {
      const q = new URL(request.url).searchParams;
      const source = SourceSchema.safeParse(q.get('source'));
      const status = RunStatusSchema.safeParse(q.get('status'));
      const filters: RunListFilters = {
        source: source.success ? source.data : undefined,
        status: status.success ? status.data : undefined,
        started_from: q.get('started_from') ?? undefined,
        started_to: q.get('started_to') ?? undefined,
      };
      return guard(() => backend.list(filters));
    }),
    http.get('/api/funnel-runs/:id', ({ params }) =>
      guard(() => backend.summary(String(params.id))),
    ),
    http.post('/api/funnel-runs', async ({ request }) => {
      const body = StartRunRequestSchema.safeParse(await request.json());
      if (!body.success) {
        return HttpResponse.json(
          { error_kind: 'invalid_request', message: body.error.message },
          { status: 422 },
        );
      }
      return guard(() => backend.start(body.data));
    }),
    http.post('/api/funnel-runs/:id/resume', ({ params }) =>
      guard(() => backend.resume(String(params.id))),
    ),
    http.post('/api/funnel-runs/:id/stop', ({ params }) =>
      guard(() => backend.stop(String(params.id))),
    ),
  ];
}

export function sseHandler(backend: MockBackend): RequestHandler {
  return sse<{ message: string }>('/api/funnel-runs/:id/events', ({ request, params, client }) => {
    const cleanup = openEventStream(
      backend,
      String(params.id),
      request.headers.get('last-event-id'),
      new URL(request.url).searchParams.get('last_event_id'),
      {
        retry: (ms) => client.send({ retry: ms }),
        send: (e) => client.send({ id: String(e.seq), data: JSON.stringify(e) }),
        close: () => client.close(),
      },
    );
    request.signal.addEventListener('abort', cleanup);
    // When the page closes its EventSource, MSW cancels the response stream and closes the client
    // but does not abort the request: listen on the client's emitter (MSW 2.15 internals, pinned).
    const emitter = (client as unknown as Record<symbol, ClientEmitter | undefined>)[
      Symbol.for('kClientEmitter')
    ];
    if (!emitter) console.warn('[mock] MSW client emitter missing: closed streams will leak');
    emitter?.on('close', cleanup);
    emitter?.on('error', cleanup);
  });
}

interface ClientEmitter {
  on(type: 'close' | 'error', listener: () => void): void;
}
