import { useCallback, useEffect, useRef, useState } from 'react';
import { sidecarFetch } from './sidecarFetch';
import { toSetupUiState, type CanonicalSetupState, type SetupUiState } from './setupBanner';

const STATUS_KEYS = [
  'schema_version',
  'active',
  'profile_id',
  'profile_digest',
  'display_hints',
  'raw_text_logged',
  'external_send_zero',
] as const;
const PROFILE_ID = /^[A-Za-z0-9._:-]{1,128}$/;
const SHA256 = /^[0-9a-f]{64}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function parseCompanySetupStatus(value: unknown): CanonicalSetupState {
  if (!isRecord(value)) throw new Error('COMPANY_SETUP_SCHEMA_INVALID');
  const keys = Object.keys(value);
  if (
    keys.length !== STATUS_KEYS.length
    || STATUS_KEYS.some(key => !(key in value))
    || value.schema_version !== 'company_profile.status.v1'
    || typeof value.active !== 'boolean'
    || !isRecord(value.display_hints)
    || value.raw_text_logged !== false
    || value.external_send_zero !== true
  ) {
    throw new Error('COMPANY_SETUP_SCHEMA_INVALID');
  }
  if (value.active) {
    if (
      typeof value.profile_id !== 'string'
      || !PROFILE_ID.test(value.profile_id)
      || typeof value.profile_digest !== 'string'
      || !SHA256.test(value.profile_digest)
    ) {
      throw new Error('COMPANY_SETUP_SCHEMA_INVALID');
    }
    return { status: 'complete' };
  }
  if (value.profile_id !== null || value.profile_digest !== null) {
    throw new Error('COMPANY_SETUP_SCHEMA_INVALID');
  }
  return { status: 'incomplete' };
}

export function useSetupState(): SetupUiState {
  const generation = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const [state, setState] = useState<SetupUiState>({ kind: 'resolving' });

  const resolve = useCallback(async () => {
    const current = generation.current + 1;
    generation.current = current;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setState({ kind: 'resolving' });
    try {
      const response = await sidecarFetch('/v1/company-profile/status', {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error('COMPANY_SETUP_HTTP_ERROR');
      const contentType = response.headers.get('content-type') ?? '';
      if (!/^application\/json(?:;|$)/i.test(contentType)) {
        throw new Error('COMPANY_SETUP_CONTENT_TYPE_INVALID');
      }
      const parsed = parseCompanySetupStatus(await response.json());
      if (current === generation.current) setState(toSetupUiState(parsed));
    } catch {
      if (current === generation.current && !controller.signal.aborted) {
        setState(toSetupUiState(undefined));
      }
    }
  }, []);

  useEffect(() => {
    void resolve();
    return () => {
      generation.current += 1;
      abort.current?.abort();
    };
  }, [resolve]);

  return state;
}
