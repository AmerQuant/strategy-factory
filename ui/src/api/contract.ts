/**
 * The T17a API contract (docs/tasks/T17a_ui_frontend.md §3), written once as zod schemas.
 *
 * The client validates every response with these (D-783) and the mock builds its responses from the
 * inferred types, so the mock cannot drift from the contract without a type error. Unknown fields are
 * stripped (ignored), never an error (§3.1 forward compatibility).
 */
import { z } from 'zod';

export const SourceSchema = z.enum(['real', 'null', 'planted']);
export const TimeframeSchema = z.enum(['1D', '1H']);
export const ArmSchema = z.enum(['real', 'control']);
export const RunStatusSchema = z.enum(['queued', 'running', 'finished', 'failed', 'stopped']);
/** Not enumerated by §3.3; the mock uses these (raised in the review). */
export const StageRunStatusSchema = z.enum(['running', 'finished', 'failed', 'stopped']);

export type Source = z.infer<typeof SourceSchema>;
export type Timeframe = z.infer<typeof TimeframeSchema>;
export type Arm = z.infer<typeof ArmSchema>;
export type RunStatus = z.infer<typeof RunStatusSchema>;
export type StageRunStatus = z.infer<typeof StageRunStatusSchema>;

export const CodeVersionSchema = z.object({ git_sha: z.string(), dirty: z.boolean() });
export type CodeVersion = z.infer<typeof CodeVersionSchema>;

export const PlanEntrySchema = z.object({
  stage_id: z.string(),
  timeframe: TimeframeSchema,
  arm: ArmSchema,
});
export type PlanEntry = z.infer<typeof PlanEntrySchema>;

/** The `funnel_started` fields (§3.1), shared by the event and the run summary (§3.3). */
const funnelStartedFields = {
  name: z.string(),
  config_id: z.string(),
  config_hash: z.string(),
  profile_hash: z.string().nullable(),
  code_version: CodeVersionSchema,
  source: SourceSchema,
  seed: z.number().int().nullable(),
  control: z.boolean(),
  plan: z.array(PlanEntrySchema),
};

// ---------------------------------------------------------------------------------------------
// §3.1 Progress events
// ---------------------------------------------------------------------------------------------

const eventBase = {
  /** Fixed at 1 (§3.1): an event of another version is a contract error, not parsed as v1. */
  schema_version: z.literal(1),
  funnel_run_id: z.uuid(),
  seq: z.number().int().positive(),
  ts: z.iso.datetime(),
};

export const FunnelStartedSchema = z.object({
  ...eventBase,
  type: z.literal('funnel_started'),
  ...funnelStartedFields,
});
export const FunnelResumedSchema = z.object({
  ...eventBase,
  type: z.literal('funnel_resumed'),
  code_version: CodeVersionSchema,
});
export const StageStartedSchema = z.object({
  ...eventBase,
  type: z.literal('stage_started'),
  stage_id: z.string(),
  timeframe: TimeframeSchema,
  arm: ArmSchema,
  stage_run_id: z.string(),
  units_total: z.number().int().nonnegative(),
  unit_kind: z.string(),
  reused: z.boolean(),
});
export const ProgressSchema = z.object({
  ...eventBase,
  type: z.literal('progress'),
  stage_run_id: z.string(),
  units_done: z.number().int().nonnegative(),
  units_total: z.number().int().nonnegative(),
  elapsed_s: z.number().nonnegative(),
  eta_s: z.number().nonnegative().nullable(),
});
export const StageFinishedSchema = z.object({
  ...eventBase,
  type: z.literal('stage_finished'),
  stage_run_id: z.string(),
  elapsed_s: z.number().nonnegative(),
  n_in: z.number().int().nonnegative(),
  n_passed: z.number().int().nonnegative(),
});
export const StageFailedSchema = z.object({
  ...eventBase,
  type: z.literal('stage_failed'),
  stage_run_id: z.string(),
  elapsed_s: z.number().nonnegative(),
  error_kind: z.string(),
  message: z.string(),
});
export const FunnelFinishedSchema = z.object({
  ...eventBase,
  type: z.literal('funnel_finished'),
  elapsed_s: z.number().nonnegative(),
});
export const FunnelFailedSchema = z.object({
  ...eventBase,
  type: z.literal('funnel_failed'),
  elapsed_s: z.number().nonnegative(),
  error_kind: z.string(),
  message: z.string(),
});
export const FunnelStoppedSchema = z.object({
  ...eventBase,
  type: z.literal('funnel_stopped'),
  elapsed_s: z.number().nonnegative(),
  stage_run_id: z.string().nullable(),
});

export const KnownEventSchema = z.discriminatedUnion('type', [
  FunnelStartedSchema,
  FunnelResumedSchema,
  StageStartedSchema,
  ProgressSchema,
  StageFinishedSchema,
  StageFailedSchema,
  FunnelFinishedSchema,
  FunnelFailedSchema,
  FunnelStoppedSchema,
]);
export type KnownEvent = z.infer<typeof KnownEventSchema>;
export type FunnelStarted = z.infer<typeof FunnelStartedSchema>;
export type StageStarted = z.infer<typeof StageStartedSchema>;

export const KNOWN_EVENT_TYPES: ReadonlySet<string> = new Set(
  KnownEventSchema.options.map((o) => o.shape.type.value),
);

/** An event whose `type` this UI does not know: shown in the log, never dropped (§3.1). */
export const UnknownEventSchema = z.looseObject({
  ...eventBase,
  type: z.string(),
});
export type UnknownEvent = z.infer<typeof UnknownEventSchema> & { unknown: true };

export type RunEvent = KnownEvent | UnknownEvent;

export function isUnknownEvent(e: RunEvent): e is UnknownEvent {
  return 'unknown' in e;
}

/**
 * Parses one event. Known types are validated strictly; an unknown `type` with a valid envelope is
 * kept as an UnknownEvent. Throws a ZodError for a malformed known event or a bad envelope.
 */
export function parseEvent(raw: unknown): RunEvent {
  const envelope = UnknownEventSchema.parse(raw);
  if (KNOWN_EVENT_TYPES.has(envelope.type)) return KnownEventSchema.parse(raw);
  return { ...envelope, unknown: true };
}

// ---------------------------------------------------------------------------------------------
// §3.3 Endpoints
// ---------------------------------------------------------------------------------------------

export const StageRunSummarySchema = z.object({
  stage_id: z.string(),
  timeframe: TimeframeSchema,
  arm: ArmSchema,
  stage_run_id: z.string(),
  status: StageRunStatusSchema,
  reused: z.boolean(),
  elapsed_s: z.number().nonnegative().nullable(),
  n_in: z.number().int().nonnegative().nullable(),
  n_passed: z.number().int().nonnegative().nullable(),
});
export type StageRunSummary = z.infer<typeof StageRunSummarySchema>;

const runCommon = {
  funnel_run_id: z.uuid(),
  ...funnelStartedFields,
  status: RunStatusSchema,
  started_at: z.iso.datetime().nullable(),
  finished_at: z.iso.datetime().nullable(),
  elapsed_s: z.number().nonnegative().nullable(),
};

export const RunSummarySchema = z.object({
  ...runCommon,
  stage_runs: z.array(StageRunSummarySchema),
});
export type RunSummary = z.infer<typeof RunSummarySchema>;

/**
 * "Per-stage-id counts real against control" (§3.3): the field name and shape are not fixed by the
 * contract; this is the mock's (raised in the review). `real` / `control` are the passes summed over
 * the timeframes, null when that arm did not finish the stage.
 */
export const StageCountSchema = z.object({
  stage_id: z.string(),
  real: z.number().int().nonnegative().nullable(),
  control: z.number().int().nonnegative().nullable(),
});
export type StageCount = z.infer<typeof StageCountSchema>;

export const RunListItemSchema = z.object({
  ...runCommon,
  stage_counts: z.array(StageCountSchema),
});
export type RunListItem = z.infer<typeof RunListItemSchema>;
export const RunListSchema = z.array(RunListItemSchema);

/** Filters of `GET /api/funnel-runs` (§3.3 names them; the parameter names are the mock's). */
export interface RunListFilters {
  source?: Source;
  status?: RunStatus;
  started_from?: string;
  started_to?: string;
}

export const StartRunRequestSchema = z.object({
  config: z.string(),
  source: SourceSchema,
  seed: z.number().int().nullable(),
  control: z.boolean(),
});
export type StartRunRequest = z.infer<typeof StartRunRequestSchema>;

export const RunIdResponseSchema = z.object({ funnel_run_id: z.uuid() });
export type RunIdResponse = z.infer<typeof RunIdResponseSchema>;

export const FunnelConfigSchema = z.object({
  id: z.string(),
  name: z.string(),
  config_hash: z.string(),
  stages: z.array(z.string()),
  timeframes: z.array(TimeframeSchema),
  universe: z.object({ name: z.string(), n_symbols: z.number().int().nonnegative() }),
  /** Its shape is not fixed by §3.3; shown as given. */
  planted_ladder: z.unknown().nullable(),
});
export type FunnelConfig = z.infer<typeof FunnelConfigSchema>;
export const FunnelConfigListSchema = z.array(FunnelConfigSchema);

export const BannerSchema = z.object({
  id: z.string(),
  level: z.string(),
  title: z.string(),
  text: z.string(),
});
export type Banner = z.infer<typeof BannerSchema>;

export const ServerStatusSchema = z.object({
  server: z.object({ host: z.string(), version: z.string() }),
  banners: z.array(BannerSchema),
});
export type ServerStatus = z.infer<typeof ServerStatusSchema>;

/** A refused request: HTTP 409 or 422 (§3.3). */
export const ApiErrorBodySchema = z.object({ error_kind: z.string(), message: z.string() });
export type ApiErrorBody = z.infer<typeof ApiErrorBodySchema>;

export const TERMINAL_EVENT_TYPES = new Set(['funnel_finished', 'funnel_failed', 'funnel_stopped']);
