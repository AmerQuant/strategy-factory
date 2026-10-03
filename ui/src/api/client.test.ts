/** D-774: every response is validated at the boundary; unknown fields are ignored. */
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { startMockServer } from '../test/render';
import { api, ApiError, ContractError } from './client';

let mock: ReturnType<typeof startMockServer>;
beforeEach(() => {
  mock = startMockServer();
});
afterEach(() => mock.close());

describe('T17a-FE API client', () => {
  it('rejects a response that does not match the contract', async () => {
    mock.server.use(http.get('/api/status', () => HttpResponse.json({ server: { host: 1 } })));
    await expect(api.status()).rejects.toBeInstanceOf(ContractError);
  });

  it('ignores unknown fields in a response', async () => {
    mock.server.use(
      http.get('/api/status', () =>
        HttpResponse.json({
          server: { host: 'h', version: 'v', uptime: 3 },
          banners: [],
          extra: true,
        }),
      ),
    );
    expect(await api.status()).toEqual({ server: { host: 'h', version: 'v' }, banners: [] });
  });

  it('turns a refusal into an ApiError with its error_kind and message', async () => {
    const err = await api
      .start({ config: 'funnel_smoke', source: 'null', seed: null, control: true })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 422, error_kind: 'seed_required' });
  });
});
