/**
 * RBAC Default Deny Tests
 * Verify default deny behavior (fail-closed)
 */

import { hasPermissionFromContext } from '../auth/rbac';
import { CallerContext } from '../services/auth_context';

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
  };
}

function describe(name: string, fn: () => void) {
  fn();
}

describe('RBAC Default Deny Tests', () => {
  it('should deny by default when no permissions', () => {
    const context: CallerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: [], // No permissions
    };

    const hasAccess = hasPermissionFromContext(context, 'user:read');
    expect(hasAccess).toBe(false); // Default deny
  });

  it('should deny when permission not in list', () => {
    const context: CallerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: ['user:read'], // Has user:read but not user:write
    };

    const hasAccess = hasPermissionFromContext(context, 'user:write');
    expect(hasAccess).toBe(false); // Default deny
  });

  it('should allow when permission is in list', () => {
    const context: CallerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: ['user:read', 'user:write'],
    };

    const hasAccess = hasPermissionFromContext(context, 'user:read');
    expect(hasAccess).toBe(true);
  });

  it('should deny superadmin permission to non-superadmin', () => {
    const context: CallerContext = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      roles: [],
      permissions: ['user:read'], // No iam:tenants:list_all
    };

    const hasAccess = hasPermissionFromContext(context, 'iam:tenants:list_all');
    expect(hasAccess).toBe(false); // Default deny
  });
});

// Output-based proof
// NOTE: OK keys are emitted by verification scripts (scripts/verify/verify_control_plane.sh)
// Test files should NOT emit OK keys directly
if (require.main === module) {
  // Tests are defined above
}

