/**
 * Live monitor (UI_spec §2.2): header (source, profile, control), summary, the timeline of every stage
 * run, the Gantt, the queue, the live log; actions stop and resume (D-780, D-783); open report is
 * phase 2 (D-787).
 */
import { Button, Group, Modal, Tooltip, useComputedColorScheme } from '@mantine/core';
import { IconFileReport, IconPlayerPlay, IconPlayerStop } from '@tabler/icons-react';
import { getRouteApi } from '@tanstack/react-router';
import { useEffect, useMemo, useState } from 'react';
import { ApiError } from '../api/client';
import { useResumeRun, useRun, useStopRun } from '../api/queries';
import { EChart } from '../charts/EChart';
import { ganttOption, slotLabel } from '../charts/gantt';
import { EventLog } from '../components/EventLog';
import { StageRow } from '../components/StageRow';
import {
  Banner,
  Card,
  ControlBadge,
  PhaseTag,
  SourceBadge,
  Stat,
  StatusBadge,
} from '../components/ui';
import {
  formatDateTime,
  formatDuration,
  formatEta,
  secondsBetween,
  shortId,
  stageLabel,
} from '../lib/format';
import { progressView, slotsInOrder, type RunState, type Slot } from '../run/reducer';
import { useRunStream } from '../run/runStream';
import { v } from '../theme/tokens';
import { Page } from '../app/Shell';

const route = getRouteApi('/runs/$runId');

/** The run's "now": the last event's time while it runs (the producer's clock), else its end. */
function runNowMs(run: RunState): number | null {
  const t = run.finished_at ?? run.last_ts;
  return t ? Date.parse(t) : null;
}

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null;
  const kind = error instanceof ApiError ? error.error_kind : 'error';
  const message = error instanceof Error ? error.message : String(error);
  return (
    <Banner level="critical" title={`Refused: ${kind}`} testId="refusal">
      {message}
    </Banner>
  );
}

function TimelineGroups({ slots }: { slots: Slot[] }) {
  const tfs = [...new Set(slots.map((s) => s.timeframe))];
  return (
    <div style={{ display: 'grid', gap: 14 }} data-testid="timeline">
      {tfs.map((tf) => (
        <div key={tf}>
          <div className="cap" style={{ margin: '0 0 6px 14px' }}>
            Timeframe {tf}
          </div>
          <div style={{ display: 'grid', gap: 2 }}>
            {slots
              .filter((s) => s.timeframe === tf)
              .map((s) => (
                <StageRow key={s.key} slot={s} />
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function Queue({ slots }: { slots: Slot[] }) {
  const queued = slots.filter((s) => s.status === 'queued');
  return (
    <Card
      title="Queue"
      caption={`${queued.length} stage runs waiting`}
      actions={
        <Tooltip label="Estimates for queued stages come with phase 2 (D-787)">
          <span>
            <PhaseTag phase="estimates: phase 2" />
          </span>
        </Tooltip>
      }
      testId="queue"
    >
      {queued.length === 0 ? (
        <div style={{ color: v('text-faint'), fontSize: 13 }}>Nothing waiting.</div>
      ) : (
        <div style={{ display: 'grid', gap: 6 }}>
          {queued.map((s, i) => (
            <div
              key={s.key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                fontSize: 13,
                color: v('text-secondary'),
              }}
            >
              <span className="num" style={{ color: v('text-faint'), width: 18 }}>
                {i + 1}
              </span>
              <span style={{ flex: 1 }}>{slotLabel(s)}</span>
              <span style={{ color: v('text-faint'), fontSize: 12 }}>no estimate</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export function LiveMonitorPage() {
  const { runId } = route.useParams();
  const summary = useRun(runId);
  const { stream, snapshot } = useRunStream(runId);
  const run = snapshot.run;
  const scheme = useComputedColorScheme('dark');
  const resume = useResumeRun();
  const stop = useStopRun();
  const [confirmStop, setConfirmStop] = useState(false);

  // A run resumed elsewhere (another tab, the CLI): reopen from the last applied seq.
  const serverStatus = summary.data?.status;
  useEffect(() => {
    if (serverStatus === 'running' && !stream.isOpen && run.status !== 'running') stream.reopen();
  }, [serverStatus, stream, run.status]);

  const slots = slotsInOrder(run);
  const pv = progressView(run);
  const nowMs = runNowMs(run);
  const gantt = useMemo(
    () => ganttOption(slotsInOrder(run), scheme, nowMs ?? 0),
    [run, scheme, nowMs],
  );
  const header = run.header;

  if (summary.isError && !header) {
    return (
      <Page>
        <ErrorAlert error={summary.error} />
      </Page>
    );
  }

  const status = run.status;
  const current = pv.running[0];
  const wall = secondsBetween(run.started_at, run.finished_at ?? run.last_ts);

  return (
    <Page>
      <section
        className="sf-card"
        data-testid="monitor-header"
        style={{ display: 'grid', gap: 12 }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="cap">Funnel run</div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                flexWrap: 'wrap',
                marginTop: 4,
              }}
            >
              <h2 className="section-title" style={{ fontSize: 20 }} data-testid="run-name">
                {header?.name ?? '…'}
              </h2>
              <span className="mono" style={{ color: v('text-faint'), fontSize: 12 }} title={runId}>
                {shortId(runId)}
              </span>
              <StatusBadge status={status} />
            </div>
            <div
              style={{
                display: 'flex',
                gap: 8,
                marginTop: 10,
                flexWrap: 'wrap',
                alignItems: 'center',
              }}
            >
              {header ? <SourceBadge source={header.source} seed={header.seed} /> : null}
              <span className="sf-badge" style={{ background: v('blue-bg'), color: v('blue-fg') }}>
                profile: defaults
              </span>
              {header ? <ControlBadge control={header.control} /> : null}
              {header ? (
                <span className="mono" style={{ fontSize: 11, color: v('text-faint') }}>
                  {header.config_id} · {header.config_hash.slice(0, 12)} ·{' '}
                  {header.code_version.git_sha}
                  {header.code_version.dirty ? ' (dirty)' : ''}
                </span>
              ) : null}
            </div>
          </div>
          <Group gap={8}>
            {status === 'running' ? (
              <Button
                variant="default"
                leftSection={<IconPlayerStop size={16} />}
                onClick={() => setConfirmStop(true)}
                data-testid="stop"
              >
                Stop
              </Button>
            ) : null}
            {status === 'failed' || status === 'stopped' ? (
              <Button
                className="sf-primary"
                leftSection={<IconPlayerPlay size={16} />}
                loading={resume.isPending}
                onClick={() => resume.mutate(runId, { onSuccess: () => stream.reopen() })}
                data-testid="resume"
              >
                Resume
              </Button>
            ) : null}
            <Tooltip label="The report view comes with phase 2">
              <span>
                <Button variant="default" disabled leftSection={<IconFileReport size={16} />}>
                  Open report
                </Button>
              </span>
            </Tooltip>
          </Group>
        </div>
        <ErrorAlert error={resume.error ?? stop.error} />
      </section>

      {header && header.source !== 'real' ? (
        <Banner level="warning" title="Synthetic data" testId="banner-synthetic">
          this run uses {header.source === 'null' ? 'the calibrated null' : 'planted edges'}
          {header.seed === null ? '' : ` (seed ${header.seed})`}, not market data.
        </Banner>
      ) : null}
      {header && !header.control ? (
        <Banner level="warning" title="--no-control" testId="banner-no-control">
          the reshuffled-returns control is off: no real-against-control comparison for this run
          (D-653).
        </Banner>
      ) : null}
      {run.failure ? (
        <Banner level="critical" title={`Failed: ${run.failure.error_kind}`} testId="banner-failed">
          {run.failure.message}
        </Banner>
      ) : null}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        <Stat
          label="Started"
          value={<span style={{ fontSize: 16 }}>{formatDateTime(run.started_at)}</span>}
        />
        <Stat
          label="Elapsed"
          value={formatDuration(wall)}
          sub={run.elapsed_s !== null ? `compute ${formatDuration(run.elapsed_s)}` : 'wall time'}
          testId="stat-elapsed"
        />
        <Stat
          label="Remaining"
          value={status === 'running' ? formatEta(pv.remaining_s) : '—'}
          sub={
            status === 'running'
              ? `current stage${pv.queued > 0 ? `; ${pv.queued} queued, not estimated` : ''}`
              : undefined
          }
          testId="stat-remaining"
        />
        <Stat
          label="Stage runs done"
          value={
            <span data-testid="stage-runs-done">
              {pv.done} / {pv.total}
            </span>
          }
          sub={
            current
              ? `now: ${stageLabel(current.stage_id)} ${current.timeframe} ${current.arm}`
              : undefined
          }
        />
      </div>

      <Card
        title="Stage runs"
        caption="stage × timeframe × arm"
        testId="timeline-card"
        actions={
          <span
            className="mono"
            style={{ fontSize: 11, color: v('text-faint') }}
            data-testid="connection"
          >
            {snapshot.connection}
            {snapshot.reconnects > 0 ? ` · reconnected ${snapshot.reconnects}×` : ''}
          </span>
        }
      >
        <TimelineGroups slots={slots} />
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
        <Card title="Stage runs over wall time" caption="Gantt · UTC" testId="gantt">
          <EChart
            option={gantt}
            height={Math.max(160, slots.length * 26 + 40)}
            ariaLabel="Gantt of stage runs"
          />
        </Card>
        <Queue slots={slots} />
      </div>

      <Card
        title="Live log"
        testId="log-card"
        actions={
          <span
            className="mono"
            style={{ fontSize: 11, color: v('text-faint') }}
            data-testid="log-counters"
          >
            applied {run.applied} · duplicates dropped {run.duplicatesDropped} · gaps {run.gaps}
            {snapshot.contractErrors.length > 0
              ? ` · contract errors ${snapshot.contractErrors.length}`
              : ''}
          </span>
        }
      >
        <EventLog run={run} />
      </Card>

      <Modal
        opened={confirmStop}
        onClose={() => setConfirmStop(false)}
        title="Stop this funnel run?"
        centered
      >
        <p style={{ color: v('text-secondary'), fontSize: 13, marginTop: 0 }}>
          The running stage is interrupted and its partial output discarded (never reused).
          Completed stages are kept; the run can be resumed.
        </p>
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setConfirmStop(false)}>
            Cancel
          </Button>
          <Button
            data-testid="confirm-stop"
            style={{
              background: v('danger-bg'),
              color: v('danger-fg'),
              border: `1px solid ${v('danger')}`,
            }}
            loading={stop.isPending}
            onClick={() => stop.mutate(runId, { onSettled: () => setConfirmStop(false) })}
          >
            Stop run
          </Button>
        </Group>
      </Modal>
    </Page>
  );
}
