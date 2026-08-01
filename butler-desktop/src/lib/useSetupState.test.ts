import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./sidecarFetch', () => ({ sidecarFetch: vi.fn() }));

import { sidecarFetch } from './sidecarFetch';
import { parseCompanySetupStatus, useSetupState } from './useSetupState';

const mockedFetch = vi.mocked(sidecarFetch);

const INCOMPLETE = {
  schema_version: 'company_profile.status.v1',
  active: false,
  profile_id: null,
  profile_digest: null,
  display_hints: {},
  raw_text_logged: false,
  external_send_zero: true,
} as const;

describe('company setup canonical status', () => {
  it('maps only an inactive canonical profile to incomplete', () => {
    expect(parseCompanySetupStatus(INCOMPLETE)).toEqual({ status: 'incomplete' });
  });

  it('requires a bound identity before mapping active to complete', () => {
    expect(parseCompanySetupStatus({
      ...INCOMPLETE,
      active: true,
      profile_id: 'profile-01',
      profile_digest: `sha256:${'a'.repeat(64)}`,
    })).toEqual({ status: 'complete' });
  });

  it.each([
    { ...INCOMPLETE, schema_version: 'company_profile.status.v0' },
    { ...INCOMPLETE, active: true },
    { ...INCOMPLETE, profile_id: 'unexpected' },
    { ...INCOMPLETE, raw_text_logged: true },
    { ...INCOMPLETE, external_send_zero: false },
    { ...INCOMPLETE, extra: true },
  ])('fails closed on malformed status %#', payload => {
    expect(() => parseCompanySetupStatus(payload)).toThrow(
      'COMPANY_SETUP_SCHEMA_INVALID',
    );
  });
});

describe('company setup readiness lifecycle', () => {
  beforeEach(() => mockedFetch.mockReset());

  it('waits for sidecar readiness and resolves again when it becomes ready', async () => {
    mockedFetch.mockResolvedValueOnce(new Response(JSON.stringify({
      ...INCOMPLETE,
      active: true,
      profile_id: 'profile-01',
      profile_digest: `sha256:${'a'.repeat(64)}`,
    }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }));

    const { result, rerender } = renderHook(
      ({ ready }) => useSetupState(ready),
      { initialProps: { ready: false } },
    );
    expect(result.current.state).toEqual({ kind: 'resolving' });
    expect(mockedFetch).not.toHaveBeenCalled();

    rerender({ ready: true });
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'complete' }));
    expect(mockedFetch).toHaveBeenCalledWith(
      '/v1/company-profile/status',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });
});
