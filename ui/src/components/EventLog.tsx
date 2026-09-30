/** The live log of a run: every applied event except progress; unknown types shown, not dropped. */
import { isUnknownEvent, type RunEvent } from '../api/contract';
import { slotLabel } from '../charts/gantt';
import { formatClock, formatDuration } from '../lib/format';
import type { RunState } from '../run/reducer';
import { v, type ColorToken } from '../theme/tokens';

const MAX_ROWS = 300;

function describe(e: RunEvent, run: RunState): { text: string; tone: ColorToken } {
  if (isUnknownEvent(e)) {
    const {
      schema_version: _s,
      funnel_run_id: _f,
      seq: _q,
      ts: _t,
      type: _y,
      unknown: _u,
      ...rest
    } = e;
    return { text: JSON.stringify(rest), tone: 'text-tertiary' };
  }
  const slot = (id: string) => {
    const key = run.byStageRun[id];
    const s = key === undefined ? undefined : run.slots[key];
    return s ? slotLabel(s) : id;
  };
  switch (e.type) {
    case 'funnel_started':
      return {
        text: `${e.name} · ${e.source}${e.seed === null ? '' : ` seed ${e.seed}`} · control ${e.control ? 'on' : 'off'} · ${e.plan.length} stage runs planned`,
        tone: 'text-secondary',
      };
    case 'funnel_resumed':
      return {
        text: `resumed at ${e.code_version.git_sha}${e.code_version.dirty ? ' (dirty)' : ''}`,
        tone: 'text-secondary',
      };
    case 'stage_started':
      return {
        text: `${slotLabel(e)} ${e.reused ? 'reused' : 'started'} · ${e.units_total} ${e.unit_kind}`,
        tone: e.reused ? 'text-muted' : 'text-secondary',
      };
    case 'progress':
      return {
        text: `${slot(e.stage_run_id)} ${e.units_done}/${e.units_total}`,
        tone: 'text-muted',
      };
    case 'stage_finished':
      return {
        text: `${slot(e.stage_run_id)} finished in ${formatDuration(e.elapsed_s)} · ${e.n_passed} of ${e.n_in} passed`,
        tone: 'accent-fg',
      };
    case 'stage_failed':
      return {
        text: `${slot(e.stage_run_id)} failed: ${e.error_kind}: ${e.message}`,
        tone: 'danger-fg',
      };
    case 'funnel_finished':
      return { text: `funnel finished in ${formatDuration(e.elapsed_s)}`, tone: 'accent-fg' };
    case 'funnel_failed':
      return { text: `funnel failed: ${e.error_kind}: ${e.message}`, tone: 'danger-fg' };
    case 'funnel_stopped':
      return {
        text: `funnel stopped after ${formatDuration(e.elapsed_s)}${e.stage_run_id ? ` · ${slot(e.stage_run_id)} discarded` : ''}`,
        tone: 'amber-fg',
      };
  }
}

export function EventLog({ run }: { run: RunState }) {
  const rows = run.log.slice(-MAX_ROWS).reverse();
  return (
    <div
      data-testid="event-log"
      style={{
        maxHeight: 340,
        overflowY: 'auto',
        borderRadius: 12,
        background: v('surface-sunken'),
      }}
    >
      <table className="sf-table" style={{ fontSize: 12 }}>
        <thead>
          <tr>
            <th style={{ width: 60 }}>seq</th>
            <th style={{ width: 80 }}>time</th>
            <th style={{ width: 150 }}>type</th>
            <th>detail</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => {
            const d = describe(e, run);
            const unknown = isUnknownEvent(e);
            return (
              <tr key={e.seq} data-testid={unknown ? 'log-unknown' : 'log-row'} data-seq={e.seq}>
                <td className="num" style={{ color: v('text-faint') }}>
                  {e.seq}
                </td>
                <td className="num">{formatClock(e.ts)}</td>
                <td className="mono" style={{ color: v(unknown ? 'link' : 'text-secondary') }}>
                  {e.type}
                  {unknown ? (
                    <span
                      className="cap"
                      style={{ marginLeft: 6, fontSize: 9, color: v('text-faint') }}
                    >
                      unknown
                    </span>
                  ) : null}
                </td>
                <td style={{ color: v(d.tone), whiteSpace: 'normal' }}>{d.text}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
