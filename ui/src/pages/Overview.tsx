/**
 * Overview, phase-1 skeleton (UI_spec §1): Running now and Recent runs; the KPI, funnel, data-quality
 * and universe blocks are labelled phase-2 placeholders.
 */
import { Link } from '@tanstack/react-router';
import type { RunListItem } from '../api/contract';
import { useRunList } from '../api/queries';
import { Page, primaryLink } from '../app/Shell';
import {
  Banner,
  Card,
  ControlBadge,
  Placeholder,
  ProgressBar,
  SourceBadge,
  StatusBadge,
} from '../components/ui';
import {
  formatDateTime,
  formatDuration,
  formatEta,
  percent,
  secondsBetween,
  stageLabel,
} from '../lib/format';
import { progressView, slotsInOrder } from '../run/reducer';
import { useRunStream } from '../run/runStream';
import { v } from '../theme/tokens';

function RunningNow({ item }: { item: RunListItem }) {
  const { snapshot } = useRunStream(item.funnel_run_id);
  const run = snapshot.run;
  const pv = progressView(run);
  const cur = pv.running[0];
  const queue = slotsInOrder(run).filter((s) => s.status === 'queued');
  return (
    <div data-testid="running-now" style={{ display: 'grid', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Link
          to="/runs/$runId"
          params={{ runId: item.funnel_run_id }}
          className="sf-link"
          style={{ fontWeight: 800, fontSize: 15 }}
        >
          {item.name}
        </Link>
        <SourceBadge source={item.source} seed={item.seed} />
        <ControlBadge control={item.control} />
        <StatusBadge status={run.status === 'connecting' ? item.status : run.status} />
      </div>
      {cur ? (
        <div className="sf-inset" style={{ padding: 14, display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
            <span style={{ fontWeight: 700 }}>
              {stageLabel(cur.stage_id)} · {cur.timeframe} ·{' '}
              <span style={{ color: v(cur.arm === 'real' ? 'blue-fg' : 'amber-fg') }}>
                {cur.arm}
              </span>
            </span>
            <span className="num" style={{ color: v('text-muted') }}>
              {cur.units_done} / {cur.units_total ?? '—'} {cur.unit_kind}
            </span>
          </div>
          <ProgressBar
            value={percent(cur.units_done, cur.units_total)}
            color="blue"
            label="current stage progress"
          />
          <div style={{ display: 'flex', gap: 18, fontSize: 12, color: v('text-muted') }}>
            <span>
              elapsed <b className="num">{formatDuration(cur.elapsed_s)}</b>
            </span>
            <span>
              remaining <b className="num">{formatEta(cur.eta_s)}</b>
            </span>
            <span>
              funnel{' '}
              <b className="num">
                {pv.done} / {pv.total}
              </b>{' '}
              stage runs, {formatDuration(secondsBetween(run.started_at, run.last_ts))}
            </span>
          </div>
        </div>
      ) : null}
      <div>
        <div className="cap" style={{ marginBottom: 6 }}>
          Queue · {queue.length}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {queue.slice(0, 8).map((s) => (
            <span
              key={s.key}
              className="sf-badge"
              style={{
                background: v('surface-alt'),
                color: v('text-subtle'),
                textTransform: 'none',
              }}
            >
              {stageLabel(s.stage_id)} {s.timeframe} {s.arm}
            </span>
          ))}
          {queue.length > 8 ? (
            <span style={{ color: v('text-faint'), fontSize: 12 }}>+{queue.length - 8}</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function stage3(item: RunListItem): string {
  const last = item.stage_counts[item.stage_counts.length - 1];
  if (!last || last.real === null) return '—';
  return item.control ? `${last.real} / ${last.control ?? '—'}` : String(last.real);
}

function wall(item: RunListItem): number | null {
  return secondsBetween(item.started_at, item.finished_at);
}

export function OverviewPage() {
  const runs = useRunList();
  const running = runs.data?.find((r) => r.status === 'running');
  // The contract fixes no list order: newest first here.
  const recent = [...(runs.data ?? [])]
    .sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))
    .slice(0, 10);
  return (
    <Page>
      {running && running.source !== 'real' ? (
        <Banner level="warning" title="Synthetic data" testId="banner-synthetic">
          the running funnel uses{' '}
          {running.source === 'null' ? 'the calibrated null' : 'planted edges'}.
        </Banner>
      ) : null}
      {running && !running.control ? (
        <Banner level="warning" title="--no-control" testId="banner-no-control">
          the running funnel has no reshuffled-returns control (D-653).
        </Banner>
      ) : null}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {[
          'Stage-3 candidates',
          'Control passes',
          'Null false-positive rate',
          'Open calibration items',
        ].map((label) => (
          <div
            key={label}
            className="sf-card"
            style={{ padding: '16px 20px' }}
            data-testid="kpi-placeholder"
          >
            <div className="cap">{label}</div>
            <div className="num" style={{ fontSize: 24, color: v('text-disabled'), marginTop: 6 }}>
              —
            </div>
            <div style={{ fontSize: 11, color: v('text-faint'), marginTop: 4 }}>phase 2 (T17b)</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 16 }}>
        <Card
          title="Running now"
          caption="Live funnel"
          testId="running-card"
          actions={
            running ? (
              <Link
                to="/runs/$runId"
                params={{ runId: running.funnel_run_id }}
                className="sf-link"
                style={{ fontSize: 13, fontWeight: 700 }}
              >
                Open monitor →
              </Link>
            ) : null
          }
        >
          {running ? (
            <RunningNow item={running} />
          ) : (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
              }}
            >
              <span style={{ color: v('text-muted'), fontSize: 13 }} data-testid="nothing-running">
                No funnel run is running.
              </span>
              <Link to="/runs/new" className="sf-primary" style={primaryLink}>
                New funnel run
              </Link>
            </div>
          )}
        </Card>
        <Placeholder
          title="Funnel"
          phase="phase 2"
          text="Per stage: real, calibrated null and control, per timeframe (E bars)."
        />
      </div>

      <Card title="Recent runs" caption="Last 10" testId="recent-runs" padding={0}>
        <div style={{ padding: '0 8px 8px' }}>
          <table className="sf-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Source</th>
                <th>Started</th>
                <th title="stage-3 passes, real / control">Stage 3</th>
                <th>Wall time</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((r) => (
                <tr key={r.funnel_run_id}>
                  <td>
                    <Link
                      to="/runs/$runId"
                      params={{ runId: r.funnel_run_id }}
                      className="sf-link"
                      style={{ fontWeight: 700 }}
                    >
                      {r.name}
                    </Link>
                  </td>
                  <td>
                    <SourceBadge source={r.source} />
                  </td>
                  <td className="num">{formatDateTime(r.started_at)}</td>
                  <td className="num">{stage3(r)}</td>
                  <td className="num">{r.status === 'running' ? '—' : formatDuration(wall(r))}</td>
                  <td>
                    <StatusBadge status={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Placeholder
          title="Data quality"
          phase="phase 2"
          text="ok / warning / critical per timeframe (E donut)."
        />
        <Placeholder
          title="Universe"
          phase="phase 2"
          text="Symbols in scope per market and timeframe (E bars)."
        />
      </div>
    </Page>
  );
}
