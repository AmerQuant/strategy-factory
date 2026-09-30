/** Small shared pieces drawn from the tokens (UI_tokens.md). */
import { Tooltip } from '@mantine/core';
import { IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import type { Arm, RunStatus, Source } from '../api/contract';
import type { SlotStatus } from '../run/reducer';
import { v, type ColorToken } from '../theme/tokens';

const SOURCE_STYLE: Record<Source, [bg: ColorToken, fg: ColorToken]> = {
  real: ['blue-bg', 'blue-fg'],
  null: ['amber-bg', 'amber-fg'],
  planted: ['violet-bg', 'violet'],
};

export function SourceBadge({ source, seed }: { source: Source; seed?: number | null }) {
  const [bg, fg] = SOURCE_STYLE[source];
  return (
    <span
      className="sf-badge"
      style={{ background: v(bg), color: v(fg) }}
      data-testid="source-badge"
    >
      {source}
      {seed !== null && seed !== undefined ? <span className="mono">· seed {seed}</span> : null}
    </span>
  );
}

type AnyStatus = RunStatus | SlotStatus | 'connecting';

const STATUS_STYLE: Record<AnyStatus, [bg: ColorToken, fg: ColorToken, label: string]> = {
  queued: ['surface-alt', 'text-subtle', 'queued'],
  connecting: ['surface-alt', 'text-subtle', 'connecting'],
  running: ['blue-bg', 'status-running', 'running'],
  finished: ['accent-bg', 'accent-fg', 'done'],
  failed: ['danger-bg', 'danger-fg', 'failed'],
  stopped: ['amber-bg', 'amber-fg', 'stopped'],
};

export function StatusBadge({ status }: { status: AnyStatus }) {
  const [bg, fg, label] = STATUS_STYLE[status];
  return (
    <span
      className="sf-badge"
      style={{ background: v(bg), color: v(fg) }}
      data-testid="status-badge"
    >
      {status === 'running' ? (
        <span
          className="sf-pulse"
          style={{ width: 6, height: 6, borderRadius: 3, background: v('blue') }}
        />
      ) : null}
      {label}
    </span>
  );
}

export function ArmTag({ arm }: { arm: Arm }) {
  return (
    <span
      className="cap"
      style={{ color: v(arm === 'real' ? 'blue-fg' : 'amber-fg'), letterSpacing: '0.06em' }}
    >
      {arm}
    </span>
  );
}

export function ControlBadge({ control }: { control: boolean }) {
  return control ? (
    <span className="sf-badge" style={{ background: v('surface-alt'), color: v('text-secondary') }}>
      control on
    </span>
  ) : (
    <Tooltip label="Run without the reshuffled-returns control (D-653)">
      <span className="sf-badge" style={{ background: v('amber-bg'), color: v('amber-fg') }}>
        <IconAlertTriangle size={12} stroke={2.4} /> no control
      </span>
    </Tooltip>
  );
}

export function PhaseTag({ phase }: { phase: string }) {
  return (
    <span
      className="sf-badge"
      style={{
        background: v('surface-alt'),
        color: v('text-faint'),
        padding: '3px 7px',
        fontSize: 10,
      }}
    >
      {phase}
    </span>
  );
}

export function Banner({
  level,
  title,
  children,
  testId,
}: {
  level: string;
  title: string;
  children?: ReactNode;
  testId?: string;
}) {
  const warn = level !== 'info';
  const danger = level === 'critical' || level === 'error';
  const [bg, border, fg]: ColorToken[] = danger
    ? ['danger-bg', 'danger', 'danger-fg']
    : warn
      ? ['amber-bg-2', 'amber-border', 'amber-fg']
      : ['surface-2', 'border-panel', 'text-secondary'];
  const Icon = warn ? IconAlertTriangle : IconInfoCircle;
  return (
    <div
      role="status"
      data-testid={testId}
      style={{
        display: 'flex',
        gap: 10,
        alignItems: 'flex-start',
        background: v(bg as ColorToken),
        border: `1px solid ${v(border as ColorToken)}`,
        borderRadius: 12,
        padding: '10px 14px',
      }}
    >
      <Icon size={16} color={v(fg as ColorToken)} style={{ marginTop: 2, flexShrink: 0 }} />
      <div style={{ fontSize: 13 }}>
        <span
          className={title.startsWith('--') ? 'mono' : undefined}
          style={{ fontWeight: 800, color: v(fg as ColorToken) }}
        >
          {title}
        </span>
        {children ? <span style={{ color: v('text-secondary') }}> — {children}</span> : null}
      </div>
    </div>
  );
}

export function ProgressBar({
  value,
  color,
  height = 8,
  label,
}: {
  value: number;
  color: ColorToken;
  height?: number;
  label?: string;
}) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
      style={{ background: v('track'), height, borderRadius: 6, overflow: 'hidden', width: '100%' }}
    >
      <div
        style={{
          width: `${value}%`,
          height: '100%',
          background: v(color),
          borderRadius: 6,
          transition: 'width 300ms linear',
        }}
      />
    </div>
  );
}

export function Card({
  title,
  caption,
  actions,
  children,
  testId,
  padding = 20,
}: {
  title?: ReactNode;
  caption?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  testId?: string;
  padding?: number;
}) {
  return (
    <section className="sf-card" style={{ padding }} data-testid={testId}>
      {title || actions ? (
        <header
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            marginBottom: 14,
          }}
        >
          <div>
            {caption ? (
              <div className="cap" style={{ marginBottom: 4 }}>
                {caption}
              </div>
            ) : null}
            {title ? <h2 className="section-title">{title}</h2> : null}
          </div>
          {actions}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  sub,
  testId,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  testId?: string;
}) {
  return (
    <div className="sf-card" style={{ padding: '16px 20px' }} data-testid={testId}>
      <div className="cap">{label}</div>
      <div
        className="num"
        style={{
          fontSize: 24,
          fontWeight: 600,
          color: v('text-strong'),
          marginTop: 6,
          lineHeight: 1.2,
        }}
      >
        {value}
      </div>
      {sub ? <div style={{ fontSize: 12, color: v('text-muted'), marginTop: 4 }}>{sub}</div> : null}
    </div>
  );
}

/** A labelled block of a later phase: shown, not half-built. */
export function Placeholder({
  title,
  phase,
  text,
}: {
  title: string;
  phase: string;
  text: string;
}) {
  return (
    <Card title={title} actions={<PhaseTag phase={phase} />} testId={`placeholder-${title}`}>
      <div
        style={{
          border: `1px dashed ${v('border-strong')}`,
          borderRadius: 12,
          padding: '22px 16px',
          color: v('text-faint'),
          fontSize: 13,
          textAlign: 'center',
          background: v('surface-3'),
        }}
      >
        {text}
      </div>
    </Card>
  );
}
