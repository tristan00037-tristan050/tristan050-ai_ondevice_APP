import { describe, expect, it } from 'vitest';
import { parseCompanySetupStatus } from './useSetupState';

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
      profile_digest: 'a'.repeat(64),
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
