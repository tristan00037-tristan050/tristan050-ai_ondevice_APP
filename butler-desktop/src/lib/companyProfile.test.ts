import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./sidecarFetch', () => ({ sidecarFetch: vi.fn() }));

import { buildAdminHeadersInput } from './admin_policy/contracts';
import { sidecarFetch } from './sidecarFetch';
import {
  parseCompanyProfileRegistration,
  registerCompanyProfile,
} from './companyProfile';

const mockedFetch = vi.mocked(sidecarFetch);
const DIGEST = `sha256:${'a'.repeat(64)}` as const;
const RESPONSE = {
  schema_version: 'company_profile.register.response.v1',
  profile_id: 'profile-01',
  profile_digest: DIGEST,
  display_hints: { company: '주식***' },
  raw_text_logged: false,
  plaintext_persisted: false,
  external_send_zero: true,
  a4_registry_ready: false,
  a4_registry_digest: null,
} as const;

describe('company profile product client', () => {
  beforeEach(() => mockedFetch.mockReset());

  it('posts the validated profile through the capability-aware product client', async () => {
    mockedFetch.mockResolvedValueOnce(new Response(JSON.stringify(RESPONSE), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }));
    const admin = buildAdminHeadersInput({
      role: 'admin',
      adminIdDigest: DIGEST,
      adminSessionDigest: DIGEST,
      authMethod: 'tauri_secure_invoke',
    });
    const request = {
      own_bank_holder_aliases: ['주식회사 버틀러'],
      own_company_aliases: ['버틀러'],
      own_account_numbers: ['123-456'],
      own_bank_accounts: [] as [],
    };

    await expect(registerCompanyProfile(request, admin)).resolves.toMatchObject({
      schemaVersion: 'company_profile.register.response.v1',
      profileId: 'profile-01',
      profileDigest: DIGEST,
    });
    expect(mockedFetch).toHaveBeenCalledWith(
      '/v1/company-profile/register',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Role': 'admin',
          'X-Admin-Id-Digest': DIGEST,
          'X-Admin-Session-Digest': DIGEST,
          'X-Admin-Auth-Method': 'tauri_secure_invoke',
        },
        body: JSON.stringify(request),
      },
    );
  });

  it.each([
    { ...RESPONSE, profile_digest: 'a'.repeat(64) },
    { ...RESPONSE, raw_text_logged: true },
    { ...RESPONSE, a4_registry_ready: true },
    { ...RESPONSE, extra: true },
  ])('fails closed on contradictory registration response %#', payload => {
    expect(() => parseCompanyProfileRegistration(payload)).toThrow(
      'COMPANY_PROFILE_RESPONSE_INVALID',
    );
  });
});
