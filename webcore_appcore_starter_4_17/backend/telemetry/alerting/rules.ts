/**
 * Alerting Rules
 * Rule-based alerting for telemetry metrics
 */

import { RollupBucket } from '../rollup/service';
import { rollupTelemetry } from '../rollup/service';

export type AlertCondition = 
  | { type: 'threshold'; operator: 'gt' | 'lt' | 'eq'; value: number }
  | { type: 'rate_change'; operator: 'increase' | 'decrease'; percent: number }
  | { type: 'count'; operator: 'gt' | 'lt'; value: number };

export interface AlertRule {
  id: string;
  tenant_id: string;
  name: string;
  metric_name: string;
  condition: AlertCondition;
  window_ms: number; // Time window for evaluation
  enabled: boolean;
  tags?: Record<string, string | number>;
}

export interface Alert {
  id: string;
  rule_id: string;
  tenant_id: string;
  metric_name: string;
  fired_at: Date;
  condition: AlertCondition;
  current_value: number;
  threshold_value?: number;
  metadata?: Record<string, unknown>;
}

// In-memory store (should be replaced with database in production)
const alertRules: AlertRule[] = [];
const firedAlerts: Alert[] = [];

/**
 * Create alert rule
 */
export function createAlertRule(rule: Omit<AlertRule, 'id'>): AlertRule {
  const newRule: AlertRule = {
    ...rule,
    id: `rule_${Date.now()}_${Math.random().toString(36).substring(7)}`,
  };
  alertRules.push(newRule);
  return newRule;
}

/**
 * Evaluate alert rules
 * Check if any rules should fire based on current telemetry
 */
export function evaluateAlertRules(tenantId: string): Alert[] {
  const fired: Alert[] = [];
  const now = Date.now();

  for (const rule of alertRules) {
    // Skip if not enabled or wrong tenant
    if (!rule.enabled || rule.tenant_id !== tenantId) {
      continue;
    }

    // Get rollup data for the rule's time window
    const rollup = rollupTelemetry({
      tenant_id: rule.tenant_id,
      metric_name: rule.metric_name,
      start_time: now - rule.window_ms,
      end_time: now,
      bucket_interval_ms: rule.window_ms, // Single bucket for the entire window
      tags: rule.tags,
    });

    if (rollup.length === 0) {
      continue; // No data
    }

    const bucket = rollup[0]; // Use the most recent bucket
    let shouldFire = false;
    let currentValue = 0;

    if (rule.condition.type === 'threshold') {
      if (bucket.avg !== undefined) {
        currentValue = bucket.avg;
        if (rule.condition.operator === 'gt' && bucket.avg > rule.condition.value) {
          shouldFire = true;
        } else if (rule.condition.operator === 'lt' && bucket.avg < rule.condition.value) {
          shouldFire = true;
        } else if (rule.condition.operator === 'eq' && bucket.avg === rule.condition.value) {
          shouldFire = true;
        }
      }
    } else if (rule.condition.type === 'count') {
      currentValue = bucket.count;
      if (rule.condition.operator === 'gt' && bucket.count > rule.condition.value) {
        shouldFire = true;
      } else if (rule.condition.operator === 'lt' && bucket.count < rule.condition.value) {
        shouldFire = true;
      }
    }

    if (shouldFire) {
      const alert: Alert = {
        id: `alert_${Date.now()}_${Math.random().toString(36).substring(7)}`,
        rule_id: rule.id,
        tenant_id: rule.tenant_id,
        metric_name: rule.metric_name,
        fired_at: new Date(),
        condition: rule.condition,
        current_value: currentValue,
        threshold_value: rule.condition.type === 'threshold' ? rule.condition.value : undefined,
        metadata: {
          bucket_count: bucket.count,
          bucket_start: bucket.bucket_start,
          bucket_end: bucket.bucket_end,
        },
      };

      firedAlerts.push(alert);
      fired.push(alert);
    }
  }

  return fired;
}

/**
 * Get fired alerts
 * Fail-Closed: cross-tenant access blocked
 */
export function getFiredAlerts(
  tenantId: string,
  filters?: {
    rule_id?: string;
    metric_name?: string;
    start_time?: Date;
    end_time?: Date;
  }
): Alert[] {
  return firedAlerts.filter(alert => {
    // Fail-Closed: Cross-tenant access blocked
    if (alert.tenant_id !== tenantId) {
      return false;
    }

    if (filters) {
      if (filters.rule_id && alert.rule_id !== filters.rule_id) {
        return false;
      }
      if (filters.metric_name && alert.metric_name !== filters.metric_name) {
        return false;
      }
      if (filters.start_time && alert.fired_at < filters.start_time) {
        return false;
      }
      if (filters.end_time && alert.fired_at > filters.end_time) {
        return false;
      }
    }

    return true;
  });
}

/**
 * Clear alerts (for testing only)
 */
export function clearAlerts(): void {
  alertRules.length = 0;
  firedAlerts.length = 0;
}

