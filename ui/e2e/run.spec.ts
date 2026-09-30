/**
 * T17a-FE §5 end-to-end on the mock: start a run → watch it → force a reconnect mid-stage (progress
 * neither jumps back nor repeats) → stop → resume (a finished stage reused) → a stage fails → resume →
 * the run finishes and appears in the history.
 */
import { expect, test, type Page } from '@playwright/test';
import './mockWindow';

async function unitsOf(page: Page, key: string): Promise<number> {
  const text = await page.getByTestId(`stage-row-${key}`).getByTestId('units').innerText();
  return Number(text.split('/')[0]?.replace(/[^0-9]/g, '') ?? 'NaN');
}

test('T17a-FE start, watch, reconnect mid-stage, stop, resume, fail, resume, finish', async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (e) => pageErrors.push(e.message));

  // A tiny synthetic funnel (6 stage runs of 1-2 simulated minutes) at 15 simulated s per real s.
  await page.goto('/runs/new?config=funnel_smoke&mockSpeed=15');
  await page.waitForFunction(() => window.__sfacMock !== undefined);

  // --- start
  await page.getByTestId('wizard-next').click(); // Profile → Source
  await page.getByTestId('source-planted').click();
  await page.getByLabel('Seed').fill('11');
  await page.getByTestId('wizard-next').click(); // → Scope
  await expect(page.getByTestId('scope')).toContainText('smoke_10');
  await page.getByTestId('wizard-next').click(); // → Control
  await page.getByTestId('wizard-next').click(); // → Review
  await expect(page.getByTestId('request-json')).toContainText('"source": "planted"');
  await page.getByTestId('start-run').click();

  // --- watch
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId('banner-synthetic')).toBeVisible();
  const first = 's01_edge|1D|real';
  const row = page.getByTestId(`stage-row-${first}`);
  await expect(row).toHaveAttribute('data-status', 'running');
  await expect(row).toHaveAttribute('data-current', 'true');
  await expect.poll(() => unitsOf(page, first)).toBeGreaterThanOrEqual(3);

  // --- force a reconnect mid-stage
  const before = await unitsOf(page, first);
  expect(before).toBeLessThan(10);
  await page.evaluate(() => window.__sfacMock?.dropConnections());
  await expect(page.getByTestId('connection')).toContainText('reconnected 1×');
  await expect(page.getByTestId('connection')).toContainText('open');
  // The browser reconnected by itself. Through MSW's service worker Chrome's Last-Event-ID header
  // does not reach the handler, so the mock replays the whole history and the client's seq dedup
  // absorbs it (D-791's second guard); the header path is proven against T17a-BE's real HTTP.
  const conns = await page.evaluate(() => window.__sfacMock?.backend.connections ?? []);
  expect(conns).toHaveLength(2);
  // Progress never goes back while the stage continues.
  let last = before;
  for (let i = 0; i < 8; i += 1) {
    const now = await unitsOf(page, first);
    expect(now).toBeGreaterThanOrEqual(last);
    last = now;
    if ((await row.getAttribute('data-status')) !== 'running') break;
    await page.waitForTimeout(150);
  }
  // The replayed history was dropped event by event; nothing was applied twice or skipped.
  const counters = await page.getByTestId('log-counters').innerText();
  expect(Number(/duplicates dropped (\d+)/.exec(counters)?.[1])).toBeGreaterThan(0);
  expect(counters).toContain('gaps 0');

  // --- stop (D-789) once the first stage is done, then resume: the finished stage is reused (D-792)
  await expect(row).toHaveAttribute('data-status', 'finished', { timeout: 30_000 });
  await page.getByTestId('stop').click();
  await page.getByTestId('confirm-stop').click();
  const header = page.getByTestId('monitor-header');
  await expect(header.getByTestId('status-badge')).toHaveText('stopped');
  await expect(page.locator('[data-status="stopped"]')).toHaveCount(1);
  await expect(page.getByTestId('stop')).toHaveCount(0);
  await expect(page.getByTestId('event-log')).toContainText('funnel_stopped');
  await page.getByTestId('resume').click();
  await expect(header.getByTestId('status-badge')).toHaveText('running');
  await expect(page.getByTestId(`stage-row-${first}`).getByTestId('reused')).toBeVisible();

  // --- a stage fails
  await page.evaluate(() => window.__sfacMock?.failNextStage());
  await expect(page.getByTestId('monitor-header').getByTestId('status-badge')).toHaveText('failed');
  await expect(page.getByTestId('banner-failed')).toContainText('InjectedFailure');
  await expect(page.getByTestId('stage-error')).toContainText('failure injected by the mock');
  const failedRow = page.locator('[data-status="failed"]');
  await expect(failedRow).toHaveCount(1);
  const failedKey = (await failedRow.getAttribute('data-testid'))?.replace('stage-row-', '') ?? '';

  // --- resume
  await page.getByTestId('resume').click();
  await expect(page.getByTestId('banner-failed')).toHaveCount(0);
  await expect(page.getByTestId(`stage-row-${failedKey}`)).toHaveAttribute(
    'data-status',
    /running|finished/,
  );
  // The fresh connection after the resume carried ?last_event_id= (D-791).
  const reopen = await page.evaluate(() => window.__sfacMock?.backend.connections.at(-1));
  expect(reopen?.last_event_id_query).toMatch(/^\d+$/);

  // --- the run finishes
  await expect(page.getByTestId('monitor-header').getByTestId('status-badge')).toHaveText('done', {
    timeout: 90_000,
  });
  await expect(page.getByTestId('stage-runs-done')).toHaveText('6 / 6');
  await expect(page.getByTestId(`stage-row-${first}`).getByTestId('reused')).toBeVisible();
  await expect(page.getByTestId('log-counters')).toContainText('gaps 0');
  const seqs = await page
    .getByTestId('log-row')
    .evaluateAll((rows) => rows.map((r) => r.getAttribute('data-seq')));
  expect(new Set(seqs).size).toBe(seqs.length);
  await expect(page.getByTestId('event-log')).toContainText('funnel_resumed');

  // --- and appears in the history as finished
  await page.getByTestId('nav-history').click();
  const newest = page.getByTestId('history-row').first();
  await expect(newest).toContainText('funnel_smoke planted seed 11');
  await expect(newest.getByTestId('status-badge')).toHaveText('done');

  expect(pageErrors).toEqual([]);
});
