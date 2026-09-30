/**
 * Routes (TanStack Router, code routes; D-781). Every page has a stable URL; the history filters live
 * in typed, validated search params, so a view can be bookmarked (UI_spec conventions).
 */
import {
  createRootRoute,
  createRoute,
  createRouter,
  type RouterHistory,
} from '@tanstack/react-router';
import { z } from 'zod';
import { HistoryPage } from '../pages/History';
import { LiveMonitorPage } from '../pages/LiveMonitor';
import { LiveRedirect } from '../pages/LiveRedirect';
import { NewRunPage } from '../pages/NewRun';
import { OverviewPage } from '../pages/Overview';
import { HistorySearchSchema, type HistorySearch } from './search';
import { Shell } from './Shell';

const rootRoute = createRootRoute({ component: Shell });

const overviewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: OverviewPage,
});

export const historyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/runs',
  validateSearch: (s: Record<string, unknown>): HistorySearch => HistorySearchSchema.parse(s),
  component: HistoryPage,
});

const NewRunSearchSchema = z.object({
  config: z.string().optional().catch(undefined),
});

export const newRunRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/runs/new',
  validateSearch: (s: Record<string, unknown>) => NewRunSearchSchema.parse(s),
  component: NewRunPage,
});

const liveRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/runs/live',
  component: LiveRedirect,
});

export const monitorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/runs/$runId',
  component: LiveMonitorPage,
});

const routeTree = rootRoute.addChildren([
  overviewRoute,
  historyRoute,
  newRunRoute,
  liveRoute,
  monitorRoute,
]);

export function createAppRouter(history?: RouterHistory) {
  return createRouter({ routeTree, defaultPreload: 'intent', history });
}

export const router = createAppRouter();

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
