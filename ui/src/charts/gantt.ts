/** The live monitor's Gantt of stage runs over wall time (UI_spec §2.2, "E Gantt"). */
import type { Slot } from '../run/reducer';
import { formatDuration, stageLabel } from '../lib/format';
import { tokenValue, type ColorToken, type Scheme } from '../theme/tokens';
import type { EChartsOption } from './EChart';

/**
 * Bar colour per status (UI_tokens.md, status colours). Stopped has no token of its own: amber, as
 * its badge (raised in the review).
 */
export const STATUS_BAR: Record<Slot['status'], ColorToken> = {
  finished: 'accent',
  running: 'blue',
  queued: 'waiting',
  failed: 'danger',
  stopped: 'amber',
};

export function slotLabel(s: Pick<Slot, 'stage_id' | 'timeframe' | 'arm'>): string {
  return `${stageLabel(s.stage_id)} · ${s.timeframe} · ${s.arm}`;
}

interface Bar {
  y: number;
  start: number;
  end: number;
  slot: Slot;
  /** The status drawn: an earlier failed or stopped attempt, or the slot's current one. */
  status: Slot['status'];
}

export function ganttBars(slots: Slot[], nowMs: number): Bar[] {
  const bars: Bar[] = [];
  slots.forEach((slot, y) => {
    for (const a of slot.earlier) {
      const status = a.status;
      bars.push({ y, start: Date.parse(a.started_at), end: Date.parse(a.ended_at), slot, status });
    }
    if (!slot.started_at) return;
    const start = Date.parse(slot.started_at);
    const end = slot.ended_at ? Date.parse(slot.ended_at) : Math.max(start, nowMs);
    bars.push({ y, start, end, slot, status: slot.status });
  });
  return bars;
}

const utcHm = (v: number) => new Date(v).toISOString().slice(11, 16);

export function ganttOption(slots: Slot[], scheme: Scheme, nowMs: number): EChartsOption {
  const t = (n: ColorToken) => tokenValue(n, scheme);
  const bars = ganttBars(slots, nowMs);
  const labels = slots.map(slotLabel);
  return {
    animation: false,
    grid: { left: 150, right: 16, top: 8, bottom: 28 },
    tooltip: {
      trigger: 'item',
      formatter: (p: { dataIndex: number }) => {
        const b = bars[p.dataIndex];
        if (!b) return '';
        const s = b.slot;
        const dur = formatDuration((b.end - b.start) / 1000);
        return `${slotLabel(s)}<br/>${b.status}${s.reused ? ' (reused)' : ''} · ${dur}<br/>${utcHm(b.start)}–${utcHm(b.end)} UTC`;
      },
    },
    xAxis: {
      type: 'time',
      axisLabel: { formatter: utcHm },
      splitLine: { show: true, lineStyle: { color: t('border') } },
    },
    yAxis: {
      type: 'category',
      data: labels,
      inverse: true,
      axisTick: { show: false },
      axisLabel: {
        fontSize: 11,
        color: (_v: string, i: number) => t(slots[i]?.arm === 'control' ? 'amber-fg' : 'blue-fg'),
      },
    },
    series: [
      {
        type: 'custom',
        encode: { x: [1, 2], y: 0 },
        data: bars.map((b) => [b.y, b.start, b.end]),
        renderItem: (
          params: { dataIndex: number },
          api: {
            value: (i: number) => number;
            coord: (v: [number, number]) => [number, number];
            size: (v: [number, number]) => [number, number];
          },
        ) => {
          const b = bars[params.dataIndex];
          if (!b) return null;
          const [x0, yc] = api.coord([api.value(1), api.value(0)]);
          const [x1] = api.coord([api.value(2), api.value(0)]);
          const h = api.size([0, 1])[1] * 0.56;
          return {
            type: 'rect',
            shape: { x: x0, y: yc - h / 2, width: Math.max(2, x1 - x0), height: h, r: 6 },
            style: {
              fill: t(STATUS_BAR[b.status]),
              opacity: b.slot.reused ? 0.55 : 1,
            },
          };
        },
      },
    ],
  };
}
