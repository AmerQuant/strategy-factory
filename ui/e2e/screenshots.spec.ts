/**
 * The review's screenshots (T17a-FE §5): every phase-1 screen in both themes, on the mock, written to
 * docs/reviews/T17a-FE/. Run with `npm run screenshots`.
 */
import { expect, test, type Page } from '@playwright/test';
import './mockWindow';
import { fileURLToPath } from 'node:url';

const OUT = fileURLToPath(new URL('../../docs/reviews/T17a-FE/', import.meta.url));
const RESUMED = 'a3d9c6e2-8b14-4f70-b5d3-2e6a9c1f0d42';
const UNKNOWN = 'e4b27d19-0f6c-4a83-9e5b-c3d1a8f27e64';

async function shot(page: Page, name: string, theme: string) {
  await page.waitForTimeout(400); // charts and transitions settle
  await page.screenshot({ path: `${OUT}${name}-${theme}.png`, fullPage: true });
}

async function ready(page: Page, path: string) {
  await page.goto(path);
  await page.waitForFunction(() => window.__sfacMock !== undefined);
  await expect(page.getByTestId('server-status')).toContainText('server on');
}

/** Client-side navigation: a reload would restart the in-page mock and lose its live runs. */
async function go(page: Page, path: string) {
  await page.evaluate((p) => {
    window.history.pushState({}, '', p);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, path);
}

async function startRun(page: Page, body: object): Promise<string> {
  return page.evaluate(async (b) => {
    const r = await fetch('/api/funnel-runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    });
    return ((await r.json()) as { funnel_run_id: string }).funnel_run_id;
  }, body);
}

for (const theme of ['dark', 'light'] as const) {
  test.describe(`${theme} theme`, () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((t) => window.localStorage.setItem('sfac-color-scheme', t), theme);
    });

    test(`screens ${theme}`, async ({ page }) => {
      // History and the idle overview.
      await ready(page, '/runs');
      await expect(page.getByTestId('history-row')).toHaveCount(5);
      await shot(page, '04-history', theme);
      await page.goto('/runs?source=real&sort=name&dir=asc');
      await expect(page.getByTestId('history-row')).toHaveCount(2);
      await shot(page, '04b-history-filtered', theme);
      await page.getByTestId('nav-overview').click();
      await expect(page.getByTestId('nothing-running')).toBeVisible();
      await shot(page, '01-overview-idle', theme);

      // Fixtures: failed-and-resumed (reused stages, the failed attempt in the Gantt) and an unknown type.
      await page.goto(`/runs/${RESUMED}`);
      await expect(page.getByTestId('stage-runs-done')).toHaveText('12 / 12');
      await shot(page, '03c-live-monitor-resumed', theme);
      await page.goto(`/runs/${UNKNOWN}`);
      await expect(page.getByTestId('log-unknown')).toHaveCount(1);
      await shot(page, '03d-live-monitor-unknown-event', theme);

      // The wizard: source, control off (D-653), review.
      await page.getByTestId('topbar-new-run').click();
      await page.getByTestId('wizard-next').click();
      await page.getByTestId('source-null').click();
      await page.getByLabel('Seed').fill('7');
      await shot(page, '02a-new-run-source', theme);
      await page.getByTestId('wizard-next').click();
      await expect(page.getByTestId('scope')).toBeVisible();
      await shot(page, '02b-new-run-scope', theme);
      await page.getByTestId('wizard-next').click();
      await page.getByRole('switch').click();
      await expect(page.getByTestId('control-warning')).toBeVisible();
      await shot(page, '02c-new-run-control-off', theme);
      await page.getByTestId('wizard-next').click();
      await shot(page, '02d-new-run-review', theme);

      // A live run of the planted pilot (T15a timings) at 120x, mid-way through stage 1's control arm.
      await page.evaluate(() => window.__sfacMock?.setSpeed(120));
      const id = await startRun(page, {
        config: 'funnel_planted_pilot',
        source: 'planted',
        seed: 20260930,
        control: true,
      });
      await go(page, `/runs/${id}`);
      await expect(page.getByTestId('stage-row-s01_edge|1D|control')).toHaveAttribute(
        'data-status',
        'running',
        {
          timeout: 30_000,
        },
      );
      await page.waitForTimeout(2500);
      await shot(page, '03a-live-monitor-running', theme);
      await page.getByTestId('nav-overview').click();
      await expect(page.getByTestId('running-now')).toBeVisible();
      await page.waitForTimeout(1500);
      await shot(page, '01b-overview-running', theme);

      // A failure, shown with its reason and the resume action.
      await go(page, `/runs/${id}`);
      await page.evaluate(() => window.__sfacMock?.failNextStage());
      await expect(page.getByTestId('resume')).toBeVisible({ timeout: 30_000 });
      await shot(page, '03b-live-monitor-failed', theme);

      // Stop (confirmation).
      await page.getByTestId('resume').click();
      await expect(page.getByTestId('stop')).toBeVisible();
      await page.getByTestId('stop').click();
      await expect(page.getByTestId('confirm-stop')).toBeVisible();
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}03e-live-monitor-stop-confirm-${theme}.png` });
    });
  });
}
