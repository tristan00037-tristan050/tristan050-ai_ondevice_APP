import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn().mockResolvedValue('test-capability-token'),
}));

import { SIDECAR_BASE } from '../constants';
import { SidecarTargetError, sidecarFetch } from '../lib/sidecarFetch';


describe('sidecarFetch target confinement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it('attaches capability only to an exact local sidecar origin and blocks redirects', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await sidecarFetch('/v1/home/runtime-status?limit=1');
    const [target, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(target.origin).toBe(new URL(SIDECAR_BASE).origin);
    expect(target.pathname).toBe('/v1/home/runtime-status');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer test-capability-token');
    expect(init.redirect).toBe('error');
  });

  it.each([
    'https://example.invalid/collect',
    '//example.invalid/collect',
    '/\\example.invalid/collect',
    'v1/home/runtime-status',
    '/v1/home/runtime-status#fragment',
    'http://user@example.invalid/collect',
  ])('rejects non-canonical or external target %s before token access', async target => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(sidecarFetch(target)).rejects.toBeInstanceOf(SidecarTargetError);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
