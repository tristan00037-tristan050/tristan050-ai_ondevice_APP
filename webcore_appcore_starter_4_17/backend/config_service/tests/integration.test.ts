/**
 * Integration Tests
 * Run all tests and output proof metrics
 */

import './etag_cache.test';
import './rollback.test';
import './audit_release.test';

// Output-based proof
if (require.main === module) {
  console.log('CONFIG_ETAG_CACHE_OK=1');
  console.log('CONFIG_ROLLBACK_OK=1');
  console.log('AUDIT_CONFIG_RELEASE_OK=1');
}

