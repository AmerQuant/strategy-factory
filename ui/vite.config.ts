import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import react from '@vitejs/plugin-react';
import type { Plugin } from 'vite';
import { defineConfig } from 'vitest/config';

const require = createRequire(import.meta.url);

/**
 * Serves MSW's worker script from node_modules in the dev server only (D-774): it is neither
 * committed nor copied into the production build.
 */
function mswWorker(): Plugin {
  return {
    name: 'sfac-msw-worker',
    apply: 'serve',
    configureServer(server) {
      const file = require.resolve('msw/mockServiceWorker.js');
      server.middlewares.use('/mockServiceWorker.js', (_req, res) => {
        res.setHeader('Content-Type', 'text/javascript');
        res.setHeader('Service-Worker-Allowed', '/');
        res.end(readFileSync(file, 'utf-8'));
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), mswWorker()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    // With the mock off (VITE_MOCK=0) the dev server proxies /api to T17a-BE (D-778).
    proxy: {
      '/api': process.env.SFAC_API_TARGET ?? 'http://127.0.0.1:8000',
    },
  },
  build: {
    chunkSizeWarningLimit: 1500,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
});
