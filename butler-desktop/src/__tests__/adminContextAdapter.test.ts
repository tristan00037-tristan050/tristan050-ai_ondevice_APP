import { describe, expect, it } from 'vitest';
import {
  AdminContextAdapterError,
  getExistingAdminContextForA2,
  normalizeAndValidateAdminContext,
} from '../lib/admin_policy/adminContext';
import type { AdminHeaders } from '../lib/admin_policy/contracts';

const DIGEST = `sha256:${'a'.repeat(64)}` as `sha256:${string}`;
const ZERO = `sha256:${'0'.repeat(64)}` as `sha256:${string}`;

describe('A-2 admin context adapter', () => {
  it('reuses the existing buildAdminHeadersInput and normalizes to the A-2 shape', () => {
    const ctx = getExistingAdminContextForA2({
      role: 'admin',
      adminIdDigest: DIGEST,
      adminSessionDigest: DIGEST,
      authMethod: 'os_keychain',
    });
    expect(ctx).toEqual({
      role: 'admin',
      admin_id_digest: DIGEST,
      admin_session_digest: DIGEST,
      auth_method: 'os_keychain',
    });
  });

  it('blocks the zero-digest placeholder before producing a context', () => {
    try {
      getExistingAdminContextForA2({
        role: 'admin',
        adminIdDigest: ZERO,
        adminSessionDigest: DIGEST,
        authMethod: 'tauri_secure_invoke',
      });
      throw new Error('should have thrown');
    } catch (error) {
      expect(error).toBeInstanceOf(AdminContextAdapterError);
      expect((error as AdminContextAdapterError).failClass).toBe('ADMIN_DIGEST_PLACEHOLDER');
    }
  });

  it('blocks the test_only auth method', () => {
    try {
      getExistingAdminContextForA2({
        role: 'admin',
        adminIdDigest: DIGEST,
        adminSessionDigest: DIGEST,
        authMethod: 'test_only',
      });
      throw new Error('should have thrown');
    } catch (error) {
      expect((error as AdminContextAdapterError).failClass).toBe('ADMIN_AUTH_METHOD_NOT_ALLOWED');
    }
  });

  it('rejects malformed digests with ADMIN_CONTEXT_INVALID', () => {
    try {
      getExistingAdminContextForA2({
        role: 'admin',
        adminIdDigest: 'not-a-digest',
        adminSessionDigest: DIGEST,
        authMethod: 'os_keychain',
      });
      throw new Error('should have thrown');
    } catch (error) {
      expect((error as AdminContextAdapterError).failClass).toBe('ADMIN_CONTEXT_INVALID');
    }
  });

  it('rejects non-admin roles with ADMIN_RBAC_DENIED', () => {
    const headers: AdminHeaders = {
      role: 'manager',
      admin_id_digest: DIGEST,
      admin_session_digest: DIGEST,
      auth_method: 'os_keychain',
    };
    try {
      normalizeAndValidateAdminContext(headers);
      throw new Error('should have thrown');
    } catch (error) {
      expect((error as AdminContextAdapterError).failClass).toBe('ADMIN_RBAC_DENIED');
    }
  });
});
