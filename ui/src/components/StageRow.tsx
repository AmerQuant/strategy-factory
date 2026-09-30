/** One stage run in the live monitor's timeline (UI_spec §2.2). */
import { IconAlertTriangle, IconRecycle } from '@tabler/icons-react';
import { STATUS_BAR, slotLabel } from '../charts/gantt';
import { formatDuration, formatEta, percent, stageLabel } from '../lib/format';
import type { Slot } from '../run/reducer';
import { v } from '../theme/tokens';
import { ArmTag, ProgressBar, StatusBadge } from './ui';

export function StageRow({ slot }: { slot: Slot }) {
  const running = slot.status === 'running';
  const pct = slot.status === 'finished' ? 100 : percent(slot.units_done, slot.units_total);
  const units =
    slot.units_total === null
      ? '—'
      : `${slot.units_done.toLocaleString('en-US')} / ${slot.units_total.toLocaleString('en-US')}`;
  let timing: string;
  if (slot.status === 'finished') timing = formatDuration(slot.elapsed_s);
  else if (running) timing = formatEta(slot.eta_s);
  else if (slot.status === 'queued') timing = 'queued';
  else timing = slot.status; // failed or stopped: the elapsed time is in its own column

  return (
    <div
      data-testid={`stage-row-${slot.key}`}
      data-status={slot.status}
      data-current={running ? 'true' : 'false'}
      aria-current={running ? 'step' : undefined}
      style={{
        display: 'grid',
        gridTemplateColumns: '170px 70px 1fr 110px 80px 170px',
        alignItems: 'center',
        gap: 14,
        padding: '10px 14px',
        borderRadius: 12,
        border: `1px solid ${running ? v('blue') : 'transparent'}`,
        background: running ? v('blue-bg') : 'transparent',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: 3,
            flexShrink: 0,
            background: v(STATUS_BAR[slot.status]),
          }}
          className={running ? 'sf-pulse' : undefined}
        />
        <span style={{ fontWeight: 700, fontSize: 13, color: v('text') }} title={slotLabel(slot)}>
          {stageLabel(slot.stage_id)}
        </span>
        <span className="mono" style={{ fontSize: 11, color: v('text-faint') }}>
          {slot.timeframe}
        </span>
      </div>
      <ArmTag arm={slot.arm} />
      <div style={{ display: 'grid', gap: 5 }}>
        <ProgressBar
          value={pct}
          color={STATUS_BAR[slot.status]}
          label={`${slotLabel(slot)} progress`}
        />
        {slot.status === 'failed' ? (
          <div
            data-testid="stage-error"
            style={{
              display: 'flex',
              gap: 6,
              fontSize: 12,
              color: v('danger-fg'),
              alignItems: 'center',
            }}
          >
            <IconAlertTriangle size={13} />
            <span className="mono" style={{ fontWeight: 600 }}>
              {slot.error_kind}
            </span>
            <span style={{ color: v('text-secondary') }}>{slot.message}</span>
          </div>
        ) : null}
      </div>
      <div className="num" style={{ fontSize: 12, color: v('text-secondary'), textAlign: 'right' }}>
        <span data-testid="units">{units}</span>
        <div style={{ fontSize: 10, color: v('text-faint') }}>{slot.unit_kind ?? ''}</div>
      </div>
      <div className="num" style={{ fontSize: 12, color: v('text-muted'), textAlign: 'right' }}>
        <span data-testid="elapsed">
          {running || slot.status === 'failed' ? formatDuration(slot.elapsed_s) : ''}
        </span>
        {slot.status === 'finished' && slot.n_passed !== null ? (
          <span data-testid="passed" title="n_passed / n_in">
            {slot.n_passed} / {slot.n_in}
          </span>
        ) : null}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 6 }}>
        {slot.reused ? (
          <span
            className="sf-badge"
            data-testid="reused"
            style={{
              background: v('surface-alt'),
              color: v('text-secondary'),
              padding: '3px 7px',
              fontSize: 10,
            }}
            title="Taken from the completed stage by the resume (D-792)"
          >
            <IconRecycle size={11} /> reused
          </span>
        ) : null}
        {slot.status === 'queued' ? (
          <StatusBadge status="queued" />
        ) : (
          <span
            className="num"
            data-testid="timing"
            style={{
              fontSize: 12,
              fontWeight: 600,
              whiteSpace: 'nowrap',
              color: v(
                slot.status === 'finished'
                  ? 'accent-fg'
                  : running
                    ? 'status-running'
                    : 'text-muted',
              ),
            }}
          >
            {timing}
          </span>
        )}
      </div>
    </div>
  );
}
