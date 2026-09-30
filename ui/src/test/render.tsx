/** Test helpers: the app's providers on a memory history, the mock API in Node (msw/node). */
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryHistory, RouterProvider } from '@tanstack/react-router';
import { render } from '@testing-library/react';
import { setupServer } from 'msw/node';
import type { ReactNode } from 'react';
import { createAppRouter } from '../app/router';
import { MockBackend } from '../mock/backend';
import { httpHandlers } from '../mock/handlers';
import { colorSchemeManager, cssVariablesResolver, theme } from '../theme/theme';

export function withMantine(children: ReactNode, rememberScheme = false) {
  return rememberScheme ? (
    <MantineProvider
      theme={theme}
      colorSchemeManager={colorSchemeManager}
      defaultColorScheme="dark"
      cssVariablesResolver={cssVariablesResolver}
    >
      {children}
    </MantineProvider>
  ) : (
    <MantineProvider
      theme={theme}
      forceColorScheme="dark"
      cssVariablesResolver={cssVariablesResolver}
    >
      {children}
    </MantineProvider>
  );
}

/** Starts msw/node over a fresh MockBackend (no event stream: Node has no EventSource). */
export function startMockServer(backend = new MockBackend()) {
  const server = setupServer(...httpHandlers(backend));
  server.listen({ onUnhandledRequest: 'error' });
  // The app calls `/api/...`; Node's fetch needs an absolute URL. Wrap MSW's patched fetch.
  const patched = globalThis.fetch;
  globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) =>
    patched(
      typeof input === 'string' ? new URL(input, window.location.href).toString() : input,
      init,
    );
  const close = () => {
    globalThis.fetch = patched;
    server.close();
    backend.dispose();
  };
  return { backend, server, close };
}

export function renderApp(path: string, rememberScheme = false) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    withMantine(
      <QueryClientProvider client={qc}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
      rememberScheme,
    ),
  );
  return { ...view, router };
}
