/** Formatting of durations, times and ids. Times are shown in UTC (CLAUDE.md rule 7). */

/** 42s · 13m 04s · 2h 07m. Null -> em dash. */
export function formatDuration(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s)) return '—';
  const total = Math.max(0, Math.round(s));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m > 0) return `${m}m ${String(sec).padStart(2, '0')}s`;
  return `${sec}s`;
}

/** An estimate of the remaining time: "~13m 04s", or "estimating…" while none is available. */
export function formatEta(s: number | null | undefined): string {
  if (s === null || s === undefined) return 'estimating…';
  return `~${formatDuration(s)}`;
}

/** 2026-09-29 19:04 UTC */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${d.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

/** 19:04:12 */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toISOString().slice(11, 19);
}

/** Seconds between two ISO times (to `now` when `to` is null). */
export function secondsBetween(
  from: string | null,
  to: string | null,
  now = Date.now(),
): number | null {
  if (!from) return null;
  const a = Date.parse(from);
  const b = to ? Date.parse(to) : now;
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return Math.max(0, (b - a) / 1000);
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

export function percent(done: number, total: number | null): number {
  if (total === null || total <= 0) return 0;
  return Math.max(0, Math.min(100, (done / total) * 100));
}

/** Stage ids as shown: s01_edge -> "S1 edge". */
export function stageLabel(stageId: string): string {
  const m = /^s0*(\d+)_?(.*)$/.exec(stageId);
  if (!m) return stageId;
  return `S${m[1]}${m[2] ? ` ${m[2].replace(/_/g, ' ')}` : ''}`;
}

/** RFC 4180 CSV. */
export function toCsv(header: string[], rows: (string | number | boolean | null)[][]): string {
  const cell = (v: string | number | boolean | null) => {
    const s = v === null ? '' : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [header, ...rows].map((r) => r.map(cell).join(',')).join('\r\n') + '\r\n';
}
