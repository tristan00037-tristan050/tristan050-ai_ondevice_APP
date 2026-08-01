import { buildAdminHeaderRecord } from './admin_policy/client';
import type { AdminHeaders, Sha256Digest } from './admin_policy/contracts';
import { sidecarFetch } from './sidecarFetch';

export type CompanyProfileRegisterRequest = Readonly<{
  own_bank_holder_aliases: string[];
  own_company_aliases: string[];
  own_account_numbers: string[];
  own_bank_accounts: [];
}>;

export type CompanyProfileRegisterResponse = Readonly<{
  schemaVersion: 'company_profile.register.response.v1';
  profileId: string;
  profileDigest: Sha256Digest;
  displayHints: Readonly<Record<string, unknown>>;
  rawTextLogged: false;
  plaintextPersisted: false;
  externalSendZero: true;
  a4RegistryReady: boolean;
  a4RegistryDigest: Sha256Digest | null;
}>;

export type CompanyProfileErrorCode =
  | 'COMPANY_PROFILE_HTTP_ERROR'
  | 'COMPANY_PROFILE_CONTENT_TYPE_INVALID'
  | 'COMPANY_PROFILE_RESPONSE_INVALID'
  | 'COMPANY_PROFILE_REQUEST_INVALID';

const RESPONSE_KEYS = [
  'schema_version',
  'profile_id',
  'profile_digest',
  'display_hints',
  'raw_text_logged',
  'plaintext_persisted',
  'external_send_zero',
  'a4_registry_ready',
  'a4_registry_digest',
] as const;
const PROFILE_ID = /^[A-Za-z0-9._:-]{1,128}$/;
const SHA256 = /^sha256:[0-9a-f]{64}$/;

export class CompanyProfileError extends Error {
  constructor(readonly code: CompanyProfileErrorCode) {
    super(code);
    this.name = 'CompanyProfileError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function validRuntimeValues(values: string[], required: boolean): boolean {
  return (
    Array.isArray(values)
    && (!required || values.length > 0)
    && values.length <= 50
    && values.every(value => (
      typeof value === 'string'
      && value.length >= 1
      && value.length <= 128
      && value === value.trim()
    ))
  );
}

function validateRequest(request: CompanyProfileRegisterRequest): void {
  if (
    !validRuntimeValues(request.own_bank_holder_aliases, true)
    || !validRuntimeValues(request.own_company_aliases, true)
    || !validRuntimeValues(request.own_account_numbers, false)
    || !Array.isArray(request.own_bank_accounts)
    || request.own_bank_accounts.length !== 0
  ) {
    throw new CompanyProfileError('COMPANY_PROFILE_REQUEST_INVALID');
  }
}

export function parseCompanyProfileRegistration(
  value: unknown,
): CompanyProfileRegisterResponse {
  if (!isRecord(value)) {
    throw new CompanyProfileError('COMPANY_PROFILE_RESPONSE_INVALID');
  }
  const keys = Object.keys(value);
  const registryDigest = value.a4_registry_digest;
  if (
    keys.length !== RESPONSE_KEYS.length
    || RESPONSE_KEYS.some(key => !(key in value))
    || value.schema_version !== 'company_profile.register.response.v1'
    || typeof value.profile_id !== 'string'
    || !PROFILE_ID.test(value.profile_id)
    || typeof value.profile_digest !== 'string'
    || !SHA256.test(value.profile_digest)
    || !isRecord(value.display_hints)
    || value.raw_text_logged !== false
    || value.plaintext_persisted !== false
    || value.external_send_zero !== true
    || typeof value.a4_registry_ready !== 'boolean'
    || (
      registryDigest !== null
      && (typeof registryDigest !== 'string' || !SHA256.test(registryDigest))
    )
  ) {
    throw new CompanyProfileError('COMPANY_PROFILE_RESPONSE_INVALID');
  }
  if (
    (value.a4_registry_ready && registryDigest === null)
    || (!value.a4_registry_ready && registryDigest !== null)
  ) {
    throw new CompanyProfileError('COMPANY_PROFILE_RESPONSE_INVALID');
  }
  return Object.freeze({
    schemaVersion: 'company_profile.register.response.v1',
    profileId: value.profile_id,
    profileDigest: value.profile_digest as Sha256Digest,
    displayHints: Object.freeze({ ...value.display_hints }),
    rawTextLogged: false,
    plaintextPersisted: false,
    externalSendZero: true,
    a4RegistryReady: value.a4_registry_ready,
    a4RegistryDigest: registryDigest as Sha256Digest | null,
  });
}

export async function registerCompanyProfile(
  request: CompanyProfileRegisterRequest,
  admin: AdminHeaders,
): Promise<CompanyProfileRegisterResponse> {
  validateRequest(request);
  const response = await sidecarFetch('/v1/company-profile/register', {
    method: 'POST',
    headers: buildAdminHeaderRecord(admin),
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new CompanyProfileError('COMPANY_PROFILE_HTTP_ERROR');
  }
  const contentType = response.headers.get('content-type') ?? '';
  if (!/^application\/json(?:;|$)/i.test(contentType)) {
    throw new CompanyProfileError('COMPANY_PROFILE_CONTENT_TYPE_INVALID');
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new CompanyProfileError('COMPANY_PROFILE_RESPONSE_INVALID');
  }
  return parseCompanyProfileRegistration(payload);
}
