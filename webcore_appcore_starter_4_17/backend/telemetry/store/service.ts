/**
 * Telemetry Storage Service
 * Tenant-isolated storage with rollup support
 */

import { MetaOnlyTelemetry } from '../schema/meta_only';

export interface StoredTelemetry extends MetaOnlyTelemetry {
  id: string;
  stored_at: Date;
}

// In-memory store (should be replaced with time-series database in production)
const telemetryStore: StoredTelemetry[] = [];

/**
 * Store telemetry
 * Fail-Closed: cross-tenant access blocked
 */
export function storeTelemetry(
  telemetry: MetaOnlyTelemetry[],
  tenantId: string
): StoredTelemetry[] {
  // Fail-Closed: Cross-tenant access blocked
  const filtered = telemetry.filter(t => t.tenant_id === tenantId);
  if (filtered.length !== telemetry.length) {
    throw new Error('Cross-tenant telemetry detected and blocked');
  }

  const stored: StoredTelemetry[] = filtered.map(t => ({
    ...t,
    id: `telemetry_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    stored_at: new Date(),
  }));

  telemetryStore.push(...stored);
  return stored;
}

/**
 * Query telemetry
 * Fail-Closed: cross-tenant access blocked
 */
export function queryTelemetry(
  tenantId: string,
  filters?: {
    metric_name?: string;
    start_time?: number;
    end_time?: number;
    tags?: Record<string, string | number>;
  }
): StoredTelemetry[] {
  return telemetryStore.filter(t => {
    // Fail-Closed: Cross-tenant access blocked
    if (t.tenant_id !== tenantId) {
      return false;
    }

    if (filters) {
      if (filters.metric_name && t.metric_name !== filters.metric_name) {
        return false;
      }
      if (filters.start_time && t.timestamp < filters.start_time) {
        return false;
      }
      if (filters.end_time && t.timestamp > filters.end_time) {
        return false;
      }
      if (filters.tags) {
        for (const [key, value] of Object.entries(filters.tags)) {
          if (!t.tags || t.tags[key] !== value) {
            return false;
          }
        }
      }
    }

    return true;
  });
}

/**
 * Clear storage (for testing only)
 */
export function clearStorage(): void {
  telemetryStore.length = 0;
}

