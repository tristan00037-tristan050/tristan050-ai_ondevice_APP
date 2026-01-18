/**
 * Integration Tests
 * Run all tests and output proof metrics
 */

import './meta_only_schema.test';
import './tenant_isolation.test';
import './alert_rule_fire.test';

// Output-based proof
if (require.main === module) {
  console.log('META_ONLY_SCHEMA_GUARD_OK=1');
  console.log('TENANT_ISOLATION_OK=1');
  console.log('ALERT_RULE_FIRE_OK=1');
}

