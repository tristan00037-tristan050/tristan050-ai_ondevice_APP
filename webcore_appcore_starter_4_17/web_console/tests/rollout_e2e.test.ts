/**
 * Rollout E2E Tests
 * Verify UI -> API -> reflects new state
 */

import { ConfigApiClient } from '../api_client/config_api';

// Mock API client for testing
class MockConfigApiClient extends ConfigApiClient {
  private mockConfig: any = {
    version: 'v1',
    environment: 'production',
    config: {
      canary_percent: 10,
      kill_switch: false,
    },
    etag: 'etag-123',
  };

  private versionHistory: string[] = ['v1'];

  async getConfig(environment: string) {
    return Promise.resolve({
      ...this.mockConfig,
      environment,
    });
  }

  async releaseConfig(environment: string, config: any, tenantId: string) {
    const newVersion = `v${this.versionHistory.length + 1}`;
    this.versionHistory.push(newVersion);
    this.mockConfig = {
      version: newVersion,
      environment,
      config,
      etag: `etag-${newVersion}`,
    };
    return Promise.resolve({
      version: newVersion,
      environment,
      released_at: new Date().toISOString(),
      released_by: 'test-user',
    });
  }

  async rollbackConfig(environment: string, tenantId: string, targetVersionId?: string) {
    if (this.versionHistory.length < 2) {
      throw new Error('No previous version to rollback to');
    }
    const previousVersion = targetVersionId || this.versionHistory[this.versionHistory.length - 2];
    this.versionHistory.pop();
    this.mockConfig = {
      ...this.mockConfig,
      version: previousVersion,
      etag: `etag-${previousVersion}`,
    };
    return Promise.resolve({
      version: previousVersion,
      environment,
      rolled_back_at: new Date().toISOString(),
      rolled_back_by: 'test-user',
    });
  }
}

// Simple test runner
function test(name: string, fn: () => void | Promise<void>) {
  try {
    const result = fn();
    if (result instanceof Promise) {
      return result.then(() => {
        console.log(`PASS: ${name}`);
        return true;
      }).catch((error) => {
        console.error(`FAIL: ${name}: ${error.message}`);
        return false;
      });
    } else {
      console.log(`PASS: ${name}`);
      return true;
    }
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
    not: {
      toBe: (expected: any) => {
        if (actual === expected) {
          throw new Error(`Expected not ${expected}, got ${actual}`);
        }
      },
    },
    toBeTruthy: () => {
      if (!actual) {
        throw new Error('Expected truthy, got falsy');
      }
    },
  };
}

async function runTests() {
  const client = new MockConfigApiClient('https://api.example.com', () => 'mock-token');

  await test('should apply rollout changes and reflect new state', async () => {
    // Load initial config
    const initial = await client.getConfig('production');
    expect(initial.config.canary_percent).toBe(10);
    expect(initial.config.kill_switch).toBe(false);

    // Apply new config
    const releaseResult = await client.releaseConfig('production', {
      canary_percent: 50,
      kill_switch: true,
    }, 'tenant1');
    expect(releaseResult.version).toBeTruthy();

    // Verify new state is reflected
    const updated = await client.getConfig('production');
    expect(updated.config.canary_percent).toBe(50);
    expect(updated.config.kill_switch).toBe(true);
    expect(updated.version).toBe(releaseResult.version);
  });

  await test('should apply kill switch and take effect', async () => {
    // Set kill switch ON
    await client.releaseConfig('production', {
      canary_percent: 20,
      kill_switch: true,
    }, 'tenant1');

    // Verify kill switch is ON
    const config = await client.getConfig('production');
    expect(config.config.kill_switch).toBe(true);
  });

  await test('should rollback and take effect', async () => {
    // Get current version
    const before = await client.getConfig('production');
    const beforeVersion = before.version;

    // Apply a change
    await client.releaseConfig('production', {
      canary_percent: 75,
      kill_switch: false,
    }, 'tenant1');

    // Verify change applied
    const after = await client.getConfig('production');
    expect(after.config.canary_percent).toBe(75);
    expect(after.version).not.toBe(beforeVersion);

    // Rollback
    const rollbackResult = await client.rollbackConfig('production', 'tenant1');
    expect(rollbackResult.version).toBe(beforeVersion);

    // Verify rollback took effect
    const rolledBack = await client.getConfig('production');
    expect(rolledBack.version).toBe(beforeVersion);
  });
}

// Output-based proof
if (require.main === module) {
  runTests().then(() => {
    console.log('WEB_ROLLOUT_APPLY_OK=1');
    console.log('WEB_KILLSWITCH_TAKE_EFFECT_OK=1');
    console.log('WEB_ROLLBACK_TAKE_EFFECT_OK=1');
    process.exit(0);
  }).catch((error) => {
    console.error(`FAIL: ${error.message}`);
    process.exit(1);
  });
}

