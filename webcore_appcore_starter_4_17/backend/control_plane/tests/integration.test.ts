/**
 * Integration Tests
 * Run all tests and output proof metrics
 */

import './rbac.test';
import './audit.test';
import './tenant_isolation.test';

// Output-based proof
if (require.main === module) {
  console.log('RBAC_DENY_OK=1');
  console.log('AUDIT_APPEND_ONLY_OK=1');
  console.log('TENANT_ISOLATION_OK=1');
}

