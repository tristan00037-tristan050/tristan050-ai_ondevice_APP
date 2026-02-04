/**
 * Rollback Tests
 * Verify config rollback to previous version
 */

// Simple test runner
function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`PASS: ${name}`);
    return true;
  } catch (error: any) {
    console.error(`FAIL: ${name}: ${error.message}`);
    return false;
  }
}

function expect(actual: any) {
  return {
    toBe: (expected: any) => {
      if (actual !== expected) {
        throw new Error(`Expected ${expected}, got ${actual}`);
      }
    },
    toBeNull: () => {
      if (actual !== null) {
        throw new Error(`Expected null, got ${actual}`);
      }
    },
    not: {
      toBeNull: () => {
        if (actual === null) {
          throw new Error('Expected not null, got null');
        }
      },
    },
  };
}

function describe(name: string, fn: () => void) {
  fn();
}

function beforeEach(fn: () => void) {
  fn();
}

import {
  createConfigVersion,
  releaseConfig,
  rollbackConfig,
  getActiveRelease,
  clearStorage,
} from '../storage/service';

describe('Rollback Tests', () => {
  beforeEach(() => {
    clearStorage();
  });

  it('should rollback to previous version', () => {
    const tenantId = 'tenant1';
    const userId = 'user1';

    // Create version 1
    const v1 = createConfigVersion({
      config_type: 'canary',
      environment: 'production',
      content: { canary_percent: 10 },
      created_by: userId,
      tenant_id: tenantId,
    });

    // Release version 1
    const r1 = releaseConfig({
      config_type: 'canary',
      environment: 'production',
      version_id: v1.id,
      tenant_id: tenantId,
      released_by: userId,
    });

    // Create version 2
    const v2 = createConfigVersion({
      config_type: 'canary',
      environment: 'production',
      content: { canary_percent: 20 },
      created_by: userId,
      tenant_id: tenantId,
    });

    // Release version 2
    const r2 = releaseConfig({
      config_type: 'canary',
      environment: 'production',
      version_id: v2.id,
      tenant_id: tenantId,
      released_by: userId,
    });

    // Verify v2 is active
    let active = getActiveRelease('canary', 'production', tenantId);
    expect(active).not.toBeNull();
    expect(active?.version_id).toBe(v2.id);

    // Rollback to v1
    const r3 = rollbackConfig({
      config_type: 'canary',
      environment: 'production',
      to_version_id: v1.id,
      tenant_id: tenantId,
      released_by: userId,
    });

    // Verify v1 is now active
    active = getActiveRelease('canary', 'production', tenantId);
    expect(active).not.toBeNull();
    expect(active?.version_id).toBe(v1.id);
    expect(active?.rollback_to_version_id).toBe(v2.id);
  });

  it('should block cross-tenant rollback', () => {
    const tenant1 = 'tenant1';
    const tenant2 = 'tenant2';
    const userId = 'user1';

    // Create version in tenant1
    const v1 = createConfigVersion({
      config_type: 'canary',
      environment: 'production',
      content: { canary_percent: 10 },
      created_by: userId,
      tenant_id: tenant1,
    });

    // Try to rollback from tenant2 (should fail)
    try {
      rollbackConfig({
        config_type: 'canary',
        environment: 'production',
        to_version_id: v1.id,
        tenant_id: tenant2,
        released_by: userId,
      });
      throw new Error('Should have thrown error');
    } catch (error: any) {
      expect(error.message).toContain('not found');
    }
  });
});


