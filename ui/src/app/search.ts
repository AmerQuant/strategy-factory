/** Typed, validated search params of the history page (D-781). */
import { z } from 'zod';
import { RunStatusSchema, SourceSchema } from '../api/contract';

export const HISTORY_COLUMNS = [
  'id',
  'name',
  'source',
  'profile',
  'config',
  'code',
  'started',
  'finished',
  'wall',
  'counts',
  'status',
] as const;
export type HistoryColumn = (typeof HISTORY_COLUMNS)[number];

export const HistorySearchSchema = z.object({
  q: z.string().optional().catch(undefined),
  source: SourceSchema.optional().catch(undefined),
  status: RunStatusSchema.optional().catch(undefined),
  from: z.iso.date().optional().catch(undefined),
  to: z.iso.date().optional().catch(undefined),
  sort: z.enum(HISTORY_COLUMNS).optional().catch(undefined),
  dir: z.enum(['asc', 'desc']).optional().catch(undefined),
  /** Hidden columns, comma-separated. */
  hide: z.string().optional().catch(undefined),
});
export type HistorySearch = z.infer<typeof HistorySearchSchema>;
