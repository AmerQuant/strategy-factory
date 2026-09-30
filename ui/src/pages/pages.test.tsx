/**
 * Pages over the mock API in Node (msw/node): the wizard's D-653 warning and a refusal shown verbatim;
 * the history filters, search and sort, held in the URL.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { renderApp, startMockServer } from '../test/render';

let mock: ReturnType<typeof startMockServer>;
beforeEach(() => {
  mock = startMockServer();
});
afterEach(() => mock.close());

async function next(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId('wizard-next'));
}

describe('T17a-FE new funnel run', () => {
  it('turning the control off shows the D-653 warning, also on the review', async () => {
    const user = userEvent.setup();
    renderApp('/runs/new');
    await screen.findByTestId('profile-defaults');
    await next(user); // → Source
    await next(user); // → Scope
    await screen.findByTestId('scope');
    await next(user); // → Control
    expect(screen.queryByTestId('control-warning')).toBeNull();
    await user.click(screen.getByRole('switch'));
    expect(await screen.findByTestId('control-warning')).toHaveTextContent('D-653');
    await next(user); // → Review
    expect(screen.getByTestId('request-json')).toHaveTextContent('"control": false');
  });

  it('shows the scope read-only from the chosen config', async () => {
    const user = userEvent.setup();
    renderApp('/runs/new?config=funnel_smoke');
    await screen.findByTestId('profile-defaults');
    await next(user);
    await next(user);
    const scope = await screen.findByTestId('scope');
    expect(scope).toHaveTextContent('smoke_10');
    expect(scope).toHaveTextContent('c07d5e2b9a1f4386');
    expect(within(scope).queryByRole('textbox')).toBeNull();
  });

  it('shows a refusal verbatim', async () => {
    mock.backend.start({ config: 'funnel_smoke', source: 'real', seed: null, control: true }); // one is running
    const user = userEvent.setup();
    renderApp('/runs/new');
    await screen.findByTestId('profile-defaults');
    for (let i = 0; i < 4; i += 1) await next(user);
    await user.click(screen.getByTestId('start-run'));
    const refusal = await screen.findByTestId('refusal');
    expect(refusal).toHaveTextContent('run_in_progress');
    expect(refusal).toHaveTextContent('is still running; one funnel run at a time');
  });

  it('a synthetic source needs a seed before Next', async () => {
    const user = userEvent.setup();
    renderApp('/runs/new');
    await screen.findByTestId('profile-defaults');
    await next(user);
    await user.click(screen.getByTestId('source-null'));
    expect(screen.getByTestId('wizard-next')).toBeDisabled();
    await user.type(screen.getByLabelText('Seed'), '7');
    expect(screen.getByTestId('wizard-next')).toBeEnabled();
  });
});

describe('T17a-FE run history', () => {
  const names = () =>
    screen.getAllByTestId('history-row').map((r) => within(r).getAllByRole('link')[0]?.textContent);

  it('lists every run, newest first', async () => {
    renderApp('/runs');
    await waitFor(() => expect(screen.getAllByTestId('history-row')).toHaveLength(5));
    expect(names()[0]).toBe('T15a planted pilot');
    expect(screen.getByTestId('history-count')).toHaveTextContent('5 of 5 runs');
  });

  it('filters by source and status from the URL (server side)', async () => {
    renderApp('/runs?source=real&status=stopped');
    await waitFor(() => expect(names()).toEqual(['Real, stopped by the user']));
  });

  it('filters by date range', async () => {
    renderApp('/runs?from=2026-09-27&to=2026-09-28');
    await waitFor(() => expect(names()).toEqual(['Null seed 7 (resumed)', 'Real, no control']));
  });

  it('searches and sorts, and the URL keeps both', async () => {
    const user = userEvent.setup();
    const { router } = renderApp('/runs');
    await waitFor(() => expect(screen.getAllByTestId('history-row')).toHaveLength(5));
    await user.type(screen.getByPlaceholderText('name, id, config, commit'), 'real');
    await waitFor(() => expect(names()).toHaveLength(2));
    expect(router.state.location.search).toMatchObject({ q: 'real' });
    await user.click(screen.getByText('Name'));
    await waitFor(() => expect(names()).toEqual(['Real, no control', 'Real, stopped by the user']));
    await user.click(screen.getByText('Name'));
    await waitFor(() => expect(names()).toEqual(['Real, stopped by the user', 'Real, no control']));
    expect(router.state.location.search).toMatchObject({ sort: 'name', dir: 'desc' });
  });

  it('shows per-stage passes real against control and flags a run without control', async () => {
    renderApp('/runs?q=no%20control');
    await waitFor(() => expect(names()).toEqual(['Real, no control']));
    const row = screen.getAllByTestId('history-row')[0];
    expect(row).toHaveTextContent('off');
  });

  it('shows id, name, source, profile, config, code, times, wall time, counts and status', async () => {
    renderApp('/runs?q=Null%20seed');
    await waitFor(() => expect(names()).toEqual(['Null seed 7 (resumed)']));
    const text = screen.getAllByTestId('history-row')[0]?.textContent?.replace(/\s+/g, ' ') ?? '';
    for (const part of [
      'a3d9c6e2', // id
      'null', // source
      'seed 7',
      'defaults', // profile
      'funnel_default · 41be07c9', // config and hash
      '6c34a01', // code version
      '2026-09-28 21:10 UTC', // started
      '2026-09-29 09:09 UTC', // finished
      '11h 59m', // wall time (includes the gap before the resume)
      'S1 18/0', // passes real / control (14 on 1D + 4 on 1H)
      'done', // status
    ]) {
      expect(text).toContain(part);
    }
  });
});

describe('T17a-FE shell', () => {
  it('shows the banners of /api/status and the server status', async () => {
    renderApp('/');
    expect(await screen.findByTestId('banner-calibration-pending')).toHaveTextContent(
      'Calibration pending (T15b)',
    );
    expect(screen.getByTestId('banner-d802-parity-gap')).toHaveTextContent('D-802 parity gap');
    await waitFor(() => expect(screen.getByTestId('server-status')).toHaveTextContent('server on'));
  });

  it('shows later phases as disabled entries with the phase that brings them', async () => {
    renderApp('/');
    await screen.findByTestId('nav-overview');
    for (const [id, phase] of [
      ['nav-funnel', 'phase 2'],
      ['nav-system', 'phase 2'],
      ['nav-profiles', 'phase 3'],
      ['nav-downloads', 'T17a-BE'],
    ] as const) {
      const entry = screen.getByTestId(id);
      expect(entry).toHaveAttribute('aria-disabled', 'true');
      expect(entry.tagName).not.toBe('A');
      expect(entry).toHaveTextContent(phase);
    }
    expect(screen.getByTestId('nav-history').tagName).toBe('A');
  });

  it('switches the theme and remembers it', async () => {
    window.localStorage.removeItem('sfac-color-scheme');
    const user = userEvent.setup();
    renderApp('/', true);
    const sw = await screen.findByTestId('theme-switch');
    expect(document.documentElement).toHaveAttribute('data-mantine-color-scheme', 'dark');
    await user.click(sw);
    expect(document.documentElement).toHaveAttribute('data-mantine-color-scheme', 'light');
    expect(window.localStorage.getItem('sfac-color-scheme')).toBe('light');
  });
});
