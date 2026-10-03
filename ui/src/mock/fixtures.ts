/**
 * Mock only: the funnel configs, their per-stage timings and the history fixtures.
 *
 * Timings of the planted funnel (D-784): the **real** T15a timings given by the supervisor are
 * 1D s01 13/12 min, s02 15/16, s03 7/7 and 1H s01 29/27, s02 real 6 (real/control). Everything marked
 * `ILLUSTRATIVE` (1H s02 control, 1H s03, every unit count and every n_in / n_passed, config names and
 * hashes, the planted ladder) is not measured: replace it from docs/streams/A.md after the next run.
 */
import type { Arm, CodeVersion, FunnelConfig, ServerStatus, Timeframe } from '../api/contract';
import type { SlotSpec } from './sim';

const MIN = 60;

export const CODE_VERSION: CodeVersion = { git_sha: '6c34a01', dirty: false };

type Row = [
  stage: string,
  tf: Timeframe,
  arm: Arm,
  minutes: number,
  units: number,
  kind: string,
  nIn: number,
  nPassed: number,
];

function slots(rows: Row[]): SlotSpec[] {
  return rows.map(
    ([stage_id, timeframe, arm, minutes, units_total, unit_kind, n_in, n_passed]) => ({
      stage_id,
      timeframe,
      arm,
      duration_s: minutes * MIN,
      units_total,
      unit_kind,
      n_in,
      n_passed,
    }),
  );
}

/** The planted funnel with T15a's real timings (minutes); counts ILLUSTRATIVE. */
export const PLANTED_PILOT_SLOTS = slots([
  ['s01_edge', '1D', 'real', 13, 486, 'profile', 486, 41],
  ['s01_edge', '1D', 'control', 12, 486, 'profile', 486, 0],
  ['s02_screen', '1D', 'real', 15, 41, 'method', 41, 23],
  ['s02_screen', '1D', 'control', 16, 36, 'method', 0, 0],
  ['s03_entry', '1D', 'real', 7, 23, 'candidate', 23, 9],
  ['s03_entry', '1D', 'control', 7, 18, 'candidate', 0, 0],
  ['s01_edge', '1H', 'real', 29, 486, 'profile', 486, 33],
  ['s01_edge', '1H', 'control', 27, 486, 'profile', 486, 0],
  ['s02_screen', '1H', 'real', 6, 33, 'method', 33, 17],
  ['s02_screen', '1H', 'control', 6, 30, 'method', 0, 0], // ILLUSTRATIVE timing
  ['s03_entry', '1H', 'real', 8, 17, 'candidate', 17, 5], // ILLUSTRATIVE timing
  ['s03_entry', '1H', 'control', 8, 15, 'candidate', 0, 0], // ILLUSTRATIVE timing
]);

/**
 * The real-data funnel (drives the resumed, no-control and stopped fixtures): ILLUSTRATIVE timings
 * (T15a's planted-funnel minutes reused, not measured on real data) and counts.
 */
export const REAL_DEFAULT_SLOTS = slots([
  ['s01_edge', '1D', 'real', 13, 486, 'profile', 486, 14],
  ['s01_edge', '1D', 'control', 12, 486, 'profile', 486, 0],
  ['s02_screen', '1D', 'real', 15, 14, 'method', 14, 6],
  ['s02_screen', '1D', 'control', 16, 12, 'method', 0, 0],
  ['s03_entry', '1D', 'real', 7, 6, 'candidate', 6, 2],
  ['s03_entry', '1D', 'control', 7, 5, 'candidate', 0, 0],
  ['s01_edge', '1H', 'real', 29, 486, 'profile', 486, 4],
  ['s01_edge', '1H', 'control', 27, 486, 'profile', 486, 0],
  ['s02_screen', '1H', 'real', 6, 4, 'method', 4, 2],
  ['s02_screen', '1H', 'control', 6, 4, 'method', 0, 0],
  ['s03_entry', '1H', 'real', 8, 2, 'candidate', 2, 1],
  ['s03_entry', '1H', 'control', 8, 2, 'candidate', 0, 0],
]);

/** A tiny synthetic funnel for the end-to-end test (ILLUSTRATIVE). */
export const SMOKE_SLOTS = slots([
  ['s01_edge', '1D', 'real', 2, 10, 'profile', 10, 4],
  ['s01_edge', '1D', 'control', 2, 10, 'profile', 10, 0],
  ['s02_screen', '1D', 'real', 2, 4, 'method', 4, 2],
  ['s02_screen', '1D', 'control', 2, 4, 'method', 0, 0],
  ['s03_entry', '1D', 'real', 1, 2, 'candidate', 2, 1],
  ['s03_entry', '1D', 'control', 1, 2, 'candidate', 0, 0],
]);

export interface MockConfig {
  config: FunnelConfig;
  slots: SlotSpec[];
}

const LADDER = {
  edge_types: ['MR', 'TF'],
  strength_atr: [1, 2, 3],
  share_of_symbols: 1.0,
}; // ILLUSTRATIVE shape (§3.3 does not fix it)

export const CONFIGS: MockConfig[] = [
  {
    config: {
      id: 'funnel_planted_pilot',
      name: 'Planted pilot (T15a)',
      config_hash: '9f3c2a71d4e8b605',
      stages: ['s01_edge', 's02_screen', 's03_entry'],
      timeframes: ['1D', '1H'],
      universe: { name: 'moneta_broker', n_symbols: 486 },
      planted_ladder: LADDER,
    },
    slots: PLANTED_PILOT_SLOTS,
  },
  {
    config: {
      id: 'funnel_default',
      name: 'Default funnel, stages 1-3',
      config_hash: '41be07c9a2d35f18',
      stages: ['s01_edge', 's02_screen', 's03_entry'],
      timeframes: ['1D', '1H'],
      universe: { name: 'moneta_broker', n_symbols: 486 },
      planted_ladder: null,
    },
    slots: REAL_DEFAULT_SLOTS,
  },
  {
    config: {
      id: 'funnel_smoke',
      name: 'Smoke (10 symbols, 1D)',
      config_hash: 'c07d5e2b9a1f4386',
      stages: ['s01_edge', 's02_screen', 's03_entry'],
      timeframes: ['1D'],
      universe: { name: 'smoke_10', n_symbols: 10 },
      planted_ladder: { edge_types: ['MR'], strength_atr: [3], share_of_symbols: 0.5 },
    },
    slots: SMOKE_SLOTS,
  },
];

export function slotsFor(configId: string, control: boolean): SlotSpec[] {
  const c = CONFIGS.find((x) => x.config.id === configId);
  if (!c) return [];
  return control ? c.slots : c.slots.filter((s) => s.arm === 'real');
}

export const SERVER_STATUS: ServerStatus = {
  server: { host: '127.0.0.1', version: 'mock (T17a-FE)' },
  banners: [
    {
      id: 'calibration-pending',
      level: 'warning',
      title: 'Calibration pending (T15b)',
      text: 'Stage 1 admits noise and misses planted edges (D-671); results are not yet calibrated against the 1 % target.',
    },
    {
      id: 'd802-parity-gap',
      level: 'warning',
      title: 'D-802 parity gap',
      text: 'An open parity gap against TradingView; see the decisions log.',
    },
  ],
}; // ILLUSTRATIVE banner texts
