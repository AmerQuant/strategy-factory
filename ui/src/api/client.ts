/**
 * The HTTP client of §3.3. Every response is validated with the contract's zod schemas (D-783): a
 * backend that drifts from the contract fails here, at the boundary, with the offending path.
 */
import type { z } from 'zod';
import {
  ApiErrorBodySchema,
  FunnelConfigListSchema,
  RunIdResponseSchema,
  RunListSchema,
  RunSummarySchema,
  ServerStatusSchema,
  type RunListFilters,
  type StartRunRequest,
} from './contract';

/** A refused request (409 / 422 `{error_kind, message}`), or another HTTP failure. */
export class ApiError extends Error {
  readonly status: number;
  readonly error_kind: string;
  constructor(status: number, error_kind: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.error_kind = error_kind;
  }
}

/** A response that does not match the contract. */
export class ContractError extends Error {
  constructor(path: string, detail: string) {
    super(`${path}: response does not match the contract: ${detail}`);
    this.name = 'ContractError';
  }
}

async function request<S extends z.ZodType>(
  path: string,
  schema: S,
  init?: RequestInit,
): Promise<z.infer<S>> {
  const res = await fetch(path, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
    },
  });
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const err = ApiErrorBodySchema.safeParse(body);
    if (err.success) throw new ApiError(res.status, err.data.error_kind, err.data.message);
    throw new ApiError(
      res.status,
      'http_error',
      `${init?.method ?? 'GET'} ${path} answered ${res.status}`,
    );
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) throw new ContractError(path, parsed.error.message);
  return parsed.data;
}

export function runListQuery(filters: RunListFilters): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (typeof v === 'string' && v !== '') q.set(k, v);
  }
  const s = q.toString();
  return s ? `?${s}` : '';
}

const post = (body?: unknown): RequestInit => ({
  method: 'POST',
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  status: () => request('/api/status', ServerStatusSchema),
  configs: () => request('/api/configs', FunnelConfigListSchema),
  listRuns: (filters: RunListFilters = {}) =>
    request(`/api/funnel-runs${runListQuery(filters)}`, RunListSchema),
  run: (id: string) => request(`/api/funnel-runs/${encodeURIComponent(id)}`, RunSummarySchema),
  start: (req: StartRunRequest) => request('/api/funnel-runs', RunIdResponseSchema, post(req)),
  resume: (id: string) =>
    request(`/api/funnel-runs/${encodeURIComponent(id)}/resume`, RunIdResponseSchema, post()),
  stop: (id: string) =>
    request(`/api/funnel-runs/${encodeURIComponent(id)}/stop`, RunIdResponseSchema, post()),
};

export function eventsUrl(id: string, lastSeq: number): string {
  const base = `/api/funnel-runs/${encodeURIComponent(id)}/events`;
  return lastSeq > 0 ? `${base}?last_event_id=${lastSeq}` : base;
}
