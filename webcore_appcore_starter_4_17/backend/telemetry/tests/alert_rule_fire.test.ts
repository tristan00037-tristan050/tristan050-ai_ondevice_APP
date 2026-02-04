/**
 * Alert Rule Fire Tests
 * Verify rule-based alerting triggers alerts
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
    toBeGreaterThan: (expected: number) => {
      if (actual <= expected) {
        throw new Error(`Expected > ${expected}, got ${actual}`);
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

import { createAlertRule, evaluateAlertRules, clearAlerts } from '../alerting/rules';
import { storeTelemetry, clearStorage } from '../store/service';
import { MetaOnlyTelemetry } from '../schema/meta_only';

describe('Alert Rule Fire Tests', () => {
  beforeEach(() => {
    clearStorage();
    clearAlerts();
  });

  it('should fire alert when threshold exceeded', () => {
    const tenantId = 'tenant1';
    const metricName = 'error_rate';

    // Create alert rule: error_rate > 0.1 (10%)
    const rule = createAlertRule({
      tenant_id: tenantId,
      name: 'High Error Rate',
      metric_name: metricName,
      condition: {
        type: 'threshold',
        operator: 'gt',
        value: 0.1,
      },
      window_ms: 60000, // 1 minute
      enabled: true,
    });

    // Store telemetry that exceeds threshold
    const telemetry: MetaOnlyTelemetry[] = [
      {
        tenant_id: tenantId,
        timestamp: Date.now() - 30000, // 30 seconds ago
        metric_name: metricName,
        metric_value: 0.15, // 15% (exceeds 10% threshold)
      },
      {
        tenant_id: tenantId,
        timestamp: Date.now() - 10000, // 10 seconds ago
        metric_name: metricName,
        metric_value: 0.12, // 12% (exceeds 10% threshold)
      },
    ];

    storeTelemetry(telemetry, tenantId);

    // Evaluate alert rules
    const fired = evaluateAlertRules(tenantId);

    expect(fired.length).toBeGreaterThan(0);
    const alert = fired.find(a => a.rule_id === rule.id);
    expect(alert).not.toBeNull();
    expect(alert?.current_value).toBeGreaterThan(0.1);
  });

  it('should fire alert when count threshold exceeded', () => {
    const tenantId = 'tenant1';
    const metricName = 'request_count';

    // Create alert rule: request_count > 1000
    const rule = createAlertRule({
      tenant_id: tenantId,
      name: 'High Request Count',
      metric_name: metricName,
      condition: {
        type: 'count',
        operator: 'gt',
        value: 1000,
      },
      window_ms: 60000, // 1 minute
      enabled: true,
    });

    // Store many telemetry points
    const telemetry: MetaOnlyTelemetry[] = [];
    for (let i = 0; i < 1500; i++) {
      telemetry.push({
        tenant_id: tenantId,
        timestamp: Date.now() - (60000 - i * 10), // Spread over 1 minute
        metric_name: metricName,
        metric_value: 1,
      });
    }

    storeTelemetry(telemetry, tenantId);

    // Evaluate alert rules
    const fired = evaluateAlertRules(tenantId);

    expect(fired.length).toBeGreaterThan(0);
    const alert = fired.find(a => a.rule_id === rule.id);
    expect(alert).not.toBeNull();
    expect(alert?.current_value).toBeGreaterThan(1000);
  });
});

