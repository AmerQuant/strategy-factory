/**
 * Mock only: starts MSW in the browser (dev server, end-to-end test). Loaded by a dynamic import that
 * exists only in development builds, so the production bundle never contains it (checked by
 * scripts/check-bundle.mjs).
 *
 * Controls for the end-to-end test: `window.__sfacMock` (speed, drop connections, inject a failure,
 * the recorded connections).
 */
import { setupWorker } from 'msw/browser';
import { MockBackend } from './backend';
import { httpHandlers, sseHandler } from './handlers';

declare global {
  interface Window {
    __sfacMock?: {
      backend: MockBackend;
      setSpeed(n: number): void;
      dropConnections(): void;
      failNextStage(): void;
    };
  }
}

function initialSpeed(): number {
  const fromUrl = new URL(window.location.href).searchParams.get('mockSpeed');
  let stored: string | null;
  try {
    stored = window.localStorage.getItem('sfac.mockSpeed');
  } catch {
    stored = null;
  }
  const n = Number(fromUrl ?? stored ?? 60);
  return Number.isFinite(n) && n > 0 ? n : 60;
}

export async function startMock(): Promise<void> {
  const backend = new MockBackend({ speed: initialSpeed(), tickMs: 200 });
  const worker = setupWorker(...httpHandlers(backend), sseHandler(backend));
  await worker.start({ onUnhandledRequest: 'bypass', quiet: true });
  window.__sfacMock = {
    backend,
    setSpeed: (n) => {
      backend.speed = n;
    },
    dropConnections: () => backend.dropConnections(),
    failNextStage: () => backend.failNextStage(),
  };
}
