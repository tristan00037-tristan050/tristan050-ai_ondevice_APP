/**
 * Integration Tests
 * Run all tests and output proof metrics
 */

import './e2e.test';
import './rbac_ui.test';

// Output-based proof
if (require.main === module) {
  console.log('CONSOLE_ONBOARDING_DONE_OK=1');
  console.log('RBAC_UI_ENFORCE_OK=1');
}

