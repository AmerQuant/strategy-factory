/**
 * New funnel run (UI_spec §2.1): Profile (disabled until T17c) → Source → Scope (read-only from the
 * chosen funnel config, D-781) → Control (off shows the D-653 warning) → Review → Start. A refusal is
 * shown verbatim (409 / 422 `{error_kind, message}`).
 */
import { Button, Group, NumberInput, Select, Stepper, Switch } from '@mantine/core';
import { IconPlayerPlay } from '@tabler/icons-react';
import { getRouteApi, useNavigate } from '@tanstack/react-router';
import { useState, type ReactNode } from 'react';
import type { FunnelConfig, Source, StartRunRequest } from '../api/contract';
import { useConfigs, useStartRun } from '../api/queries';
import { Page } from '../app/Shell';
import { Banner, Card, PhaseTag, SourceBadge } from '../components/ui';
import { stageLabel } from '../lib/format';
import { v } from '../theme/tokens';
import { ErrorAlert } from './LiveMonitor';

const route = getRouteApi('/runs/new');

const SOURCES: { source: Source; title: string; text: string }[] = [
  { source: 'real', title: 'Real data', text: 'The development segment of the store.' },
  {
    source: 'null',
    title: 'Calibrated null',
    text: 'Random walk with the real session profile; needs a seed.',
  },
  {
    source: 'planted',
    title: 'Planted',
    text: "The config's planted ladder on the null; needs a seed.",
  },
];

function SelectCard({
  selected,
  onClick,
  children,
  testId,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
  testId: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      aria-pressed={selected}
      style={{
        textAlign: 'left',
        cursor: 'pointer',
        borderRadius: 12,
        padding: 16,
        background: v(selected ? 'selected-card-bg' : 'surface-3'),
        border: `1px solid ${v(selected ? 'accent' : 'border')}`,
        color: v('text'),
        font: 'inherit',
        display: 'grid',
        gap: 8,
      }}
    >
      {children}
    </button>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '160px 1fr',
        gap: 12,
        padding: '8px 0',
        borderBottom: `1px solid ${v('border')}`,
      }}
    >
      <span className="cap" style={{ alignSelf: 'center' }}>
        {label}
      </span>
      <span style={{ fontSize: 13, color: v('text-body-2') }}>{children}</span>
    </div>
  );
}

function ScopeView({ config }: { config: FunnelConfig }) {
  return (
    <div data-testid="scope">
      <Row label="Config">
        <span className="mono">{config.id}</span> — {config.name}
      </Row>
      <Row label="Config hash">
        <span className="mono">{config.config_hash}</span>
      </Row>
      <Row label="Stages">{config.stages.map(stageLabel).join(' → ')}</Row>
      <Row label="Timeframes">{config.timeframes.join(', ')}</Row>
      <Row label="Universe">
        {config.universe.name} · <span className="num">{config.universe.n_symbols}</span> symbols
      </Row>
      <Row label="Planted ladder">
        {config.planted_ladder === null ? (
          <span style={{ color: v('text-faint') }}>none</span>
        ) : (
          <code className="mono" style={{ fontSize: 12 }}>
            {JSON.stringify(config.planted_ladder)}
          </code>
        )}
      </Row>
    </div>
  );
}

export function NewRunPage() {
  const search = route.useSearch();
  const navigate = useNavigate();
  const configs = useConfigs();
  const start = useStartRun();
  const [step, setStep] = useState(0);
  const [source, setSource] = useState<Source>('real');
  const [seed, setSeed] = useState<number | null>(null);
  const [control, setControl] = useState(true);
  const configId = search.config ?? configs.data?.[0]?.id ?? null;
  const config = configs.data?.find((c) => c.id === configId) ?? null;
  const setConfig = (id: string | null) =>
    navigate({ to: '/runs/new', search: { config: id ?? undefined }, replace: true });

  const request: StartRunRequest | null = configId
    ? { config: configId, source, seed: source === 'real' ? null : seed, control }
    : null;
  const needsSeed = source !== 'real' && seed === null;

  const submit = () => {
    if (!request) return;
    start.mutate(request, {
      onSuccess: (r) => navigate({ to: '/runs/$runId', params: { runId: r.funnel_run_id } }),
    });
  };

  const nav = (canNext = true) => (
    <Group justify="space-between" mt={20}>
      <Button variant="default" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
        Back
      </Button>
      <Button
        className="sf-primary"
        disabled={!canNext}
        onClick={() => setStep((s) => s + 1)}
        data-testid="wizard-next"
      >
        Next
      </Button>
    </Group>
  );

  return (
    <Page>
      <Card testId="wizard">
        <Stepper active={step} onStepClick={setStep} allowNextStepsSelect={false} size="sm">
          <Stepper.Step label="Profile" description="defaults">
            <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
              <SelectCard selected onClick={() => undefined} testId="profile-defaults">
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <b>Repository defaults</b>
                  <PhaseTag phase="profiles: T17c" />
                </div>
                <span style={{ fontSize: 13, color: v('text-muted') }}>
                  Saved profiles and their hashes come with phase 3; every run uses the
                  repository&apos;s configs until then.
                </span>
              </SelectCard>
            </div>
            {nav()}
          </Stepper.Step>

          <Stepper.Step label="Source" description={source}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 12,
                marginTop: 16,
              }}
            >
              {SOURCES.map((s) => (
                <SelectCard
                  key={s.source}
                  selected={source === s.source}
                  onClick={() => setSource(s.source)}
                  testId={`source-${s.source}`}
                >
                  <SourceBadge source={s.source} />
                  <b>{s.title}</b>
                  <span style={{ fontSize: 13, color: v('text-muted') }}>{s.text}</span>
                </SelectCard>
              ))}
            </div>
            {source !== 'real' ? (
              <NumberInput
                mt={16}
                maw={240}
                label="Seed"
                placeholder="e.g. 7"
                allowDecimal={false}
                allowNegative={false}
                value={seed ?? ''}
                onChange={(x) => setSeed(typeof x === 'number' ? x : null)}
                data-testid="seed"
              />
            ) : null}
            {nav(!needsSeed)}
          </Stepper.Step>

          <Stepper.Step label="Scope" description={config?.id ?? '—'}>
            <div style={{ display: 'grid', gap: 16, marginTop: 16 }}>
              <Select
                label="Funnel config"
                maw={420}
                data={(configs.data ?? []).map((c) => ({
                  value: c.id,
                  label: `${c.name} (${c.id})`,
                }))}
                value={configId}
                onChange={setConfig}
                allowDeselect={false}
                data-testid="config-select"
              />
              <div className="cap">Scope — read-only, from the config (D-781)</div>
              {config ? <ScopeView config={config} /> : null}
            </div>
            {nav(config !== null)}
          </Stepper.Step>

          <Stepper.Step label="Control" description={control ? 'on' : 'off'}>
            <div style={{ display: 'grid', gap: 14, marginTop: 16 }}>
              <Switch
                checked={control}
                onChange={(e) => setControl(e.currentTarget.checked)}
                label="Run the reshuffled-returns control arm"
                size="md"
                data-testid="control-switch"
              />
              {!control ? (
                <Banner level="warning" title="Control off (D-653)" testId="control-warning">
                  without the control arm this run has no real-against-control comparison; its
                  results cannot be told apart from what reshuffled returns would pass. The run is
                  flagged <span className="mono">--no-control</span>.
                </Banner>
              ) : null}
            </div>
            {nav()}
          </Stepper.Step>

          <Stepper.Step label="Review">
            <div style={{ display: 'grid', gap: 16, marginTop: 16 }} data-testid="review">
              <div>
                <Row label="Profile">defaults</Row>
                <Row label="Source">
                  <SourceBadge source={source} seed={source === 'real' ? null : seed} />
                </Row>
                <Row label="Control">
                  {control ? 'on' : <span className="mono">off (--no-control)</span>}
                </Row>
              </div>
              {config ? <ScopeView config={config} /> : null}
              {!control ? <Banner level="warning" title="Control off (D-653)" /> : null}
              <div>
                <div className="cap" style={{ marginBottom: 6 }}>
                  Request
                </div>
                <pre
                  className="mono"
                  data-testid="request-json"
                  style={{
                    margin: 0,
                    padding: 12,
                    borderRadius: 12,
                    background: v('surface-sunken'),
                    fontSize: 12,
                    color: v('text-secondary'),
                  }}
                >
                  {JSON.stringify(request, null, 2)}
                </pre>
              </div>
              <ErrorAlert error={start.error} />
              <Group justify="space-between">
                <Button variant="default" onClick={() => setStep((s) => s - 1)}>
                  Back
                </Button>
                <Button
                  className="sf-primary"
                  leftSection={<IconPlayerPlay size={16} />}
                  loading={start.isPending}
                  disabled={!request || needsSeed}
                  onClick={submit}
                  data-testid="start-run"
                >
                  Start
                </Button>
              </Group>
            </div>
          </Stepper.Step>
        </Stepper>
      </Card>
    </Page>
  );
}
