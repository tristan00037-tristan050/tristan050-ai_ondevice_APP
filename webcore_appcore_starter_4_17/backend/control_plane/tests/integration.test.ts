/**
 * Integration Tests
 * Run all tests and output proof metrics
 */

import './rbac.test';
import './audit.test';
import './tenant_isolation.test';

// Output-based proof
// NOTE: OK keys are emitted by verification scripts (scripts/verify/verify_svr01_control_plane.sh)
// Test files should NOT emit OK keys directly
if (require.main === module) {
  // Tests are defined above and run via describe/it calls
}

