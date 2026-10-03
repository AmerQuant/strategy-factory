/** The mock's test controls on `window` (src/mock/browser.ts), as the e2e specs see them. */
export interface MockConnection {
  last_event_id_header: string | null;
  last_event_id_query: string | null;
}

declare global {
  interface Window {
    __sfacMock?: {
      backend: { connections: MockConnection[] };
      setSpeed(n: number): void;
      dropConnections(): void;
      failNextStage(): void;
    };
  }
}
