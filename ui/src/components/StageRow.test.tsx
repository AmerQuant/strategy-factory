/** The live monitor's stage row in each state (T17a-FE §5: component tests for the progress view). */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Slot } from '../run/reducer';
import { withMantine } from '../test/render';
import { StageRow } from './StageRow';

function slot(p: Partial<Slot>): Slot {
  return {
    key: 's01_edge|1D|real',
    stage_id: 's01_edge',
    timeframe: '1D',
    arm: 'real',
    planned: true,
    status: 'queued',
    reused: false,
    stage_run_id: null,
    unit_kind: null,
    units_done: 0,
    units_total: null,
    elapsed_s: null,
    eta_s: null,
    n_in: null,
    n_passed: null,
    error_kind: null,
    message: null,
    started_at: null,
    ended_at: null,
    attempts: 0,
    earlier: [],
    ...p,
  };
}

const row = () => screen.getByTestId('stage-row-s01_edge|1D|real');
const bar = () => screen.getByRole('progressbar');

describe('T17a-FE stage row', () => {
  it('pending: queued, empty bar', () => {
    render(withMantine(<StageRow slot={slot({})} />));
    expect(row()).toHaveAttribute('data-status', 'queued');
    expect(row()).toHaveAttribute('data-current', 'false');
    expect(bar()).toHaveAttribute('aria-valuenow', '0');
    expect(screen.getByTestId('status-badge')).toHaveTextContent('queued');
  });

  it('running: highlighted, units, elapsed and estimate', () => {
    render(
      withMantine(
        <StageRow
          slot={slot({
            status: 'running',
            units_done: 243,
            units_total: 486,
            unit_kind: 'profile',
            elapsed_s: 390,
            eta_s: 385,
          })}
        />,
      ),
    );
    expect(row()).toHaveAttribute('data-current', 'true');
    expect(row()).toHaveAttribute('aria-current', 'step');
    expect(bar()).toHaveAttribute('aria-valuenow', '50');
    expect(screen.getByTestId('units')).toHaveTextContent('243 / 486');
    expect(screen.getByTestId('elapsed')).toHaveTextContent('6m 30s');
    expect(screen.getByTestId('timing')).toHaveTextContent('~6m 25s');
  });

  it('running before an estimate exists', () => {
    render(
      withMantine(
        <StageRow
          slot={slot({ status: 'running', units_done: 0, units_total: 486, elapsed_s: 3 })}
        />,
      ),
    );
    expect(screen.getByTestId('timing')).toHaveTextContent('estimating…');
  });

  it('finished: full bar, final duration and passes', () => {
    render(
      withMantine(
        <StageRow
          slot={slot({
            status: 'finished',
            units_done: 486,
            units_total: 486,
            elapsed_s: 780,
            n_in: 486,
            n_passed: 41,
          })}
        />,
      ),
    );
    expect(bar()).toHaveAttribute('aria-valuenow', '100');
    expect(screen.getByTestId('timing')).toHaveTextContent('13m 00s');
    expect(screen.getByTestId('passed')).toHaveTextContent('41 / 486');
    expect(screen.queryByTestId('reused')).toBeNull();
  });

  it('reused: flagged', () => {
    render(
      withMantine(
        <StageRow
          slot={slot({
            status: 'finished',
            reused: true,
            units_total: 10,
            units_done: 10,
            elapsed_s: 60,
          })}
        />,
      ),
    );
    expect(screen.getByTestId('reused')).toHaveTextContent('reused');
  });

  it('failed: the reason shown', () => {
    render(
      withMantine(
        <StageRow
          slot={slot({
            status: 'failed',
            units_done: 301,
            units_total: 486,
            elapsed_s: 1079,
            error_kind: 'WorkerCrashed',
            message: 'exit 137',
          })}
        />,
      ),
    );
    expect(row()).toHaveAttribute('data-status', 'failed');
    expect(screen.getByTestId('stage-error')).toHaveTextContent('WorkerCrashed');
    expect(screen.getByTestId('stage-error')).toHaveTextContent('exit 137');
    expect(screen.getByTestId('timing')).toHaveTextContent('failed');
    expect(screen.getByTestId('elapsed')).toHaveTextContent('17m 59s');
  });
});
