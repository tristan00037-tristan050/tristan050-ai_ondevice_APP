/**
 * Telemetry Ingest Service
 * Support OTLP (preferred) and JSON fallback
 */

import { IngestRequest, validateIngestRequest, MetaOnlyTelemetry } from '../schema/meta_only';
import { storeTelemetry } from '../store/service';
import { createAuditLog } from '../../control_plane/audit/service';

export interface IngestResponse {
  success: boolean;
  ingested_count: number;
  rejected_count: number;
  reason_code?: string;
  message?: string;
}

/**
 * Ingest telemetry (JSON format)
 * Fail-Closed: schema violation => rejected with reason_code, never stored
 */
export function ingestTelemetry(request: IngestRequest): IngestResponse {
  // Validate request
  const validation = validateIngestRequest(request);
  if (!validation.valid) {
    // Fail-Closed: never store invalid telemetry
    return {
      success: false,
      ingested_count: 0,
      rejected_count: request.telemetry.length,
      reason_code: validation.reason_code,
      message: validation.message,
    };
  }

  try {
    // Store telemetry
    const stored = storeTelemetry(request.telemetry, request.tenant_id);

    // Audit log
    createAuditLog({
      tenant_id: request.tenant_id,
      user_id: 'system', // System ingestion
      action: 'create',
      resource_type: 'tenant',
      resource_id: `telemetry_ingest_${Date.now()}`,
      success: true,
      metadata: {
        ingested_count: stored.length,
        metric_names: [...new Set(stored.map(t => t.metric_name))],
      },
    });

    return {
      success: true,
      ingested_count: stored.length,
      rejected_count: 0,
    };
  } catch (error: any) {
    // Fail-Closed: error during storage
    return {
      success: false,
      ingested_count: 0,
      rejected_count: request.telemetry.length,
      reason_code: 'INGEST_STORAGE_ERROR',
      message: error.message,
    };
  }
}

/**
 * Parse OTLP format (simplified)
 * In production, use OpenTelemetry SDK
 */
export function parseOTLP(payload: unknown): IngestRequest | null {
  // Simplified OTLP parser
  // In production, use @opentelemetry/otlp-transformer
  if (typeof payload !== 'object' || payload === null) {
    return null;
  }

  const obj = payload as Record<string, unknown>;
  
  // Extract tenant_id from resource attributes
  const resource = obj.resource as Record<string, unknown> | undefined;
  const tenantId = resource?.attributes?.['tenant.id'] as string | undefined;
  
  if (!tenantId) {
    return null;
  }

  // Extract metrics from scope metrics
  const scopeMetrics = obj.scopeMetrics as Array<Record<string, unknown>> | undefined;
  if (!Array.isArray(scopeMetrics)) {
    return null;
  }

  const telemetry: MetaOnlyTelemetry[] = [];

  for (const scopeMetric of scopeMetrics) {
    const metrics = scopeMetric.metrics as Array<Record<string, unknown>> | undefined;
    if (!Array.isArray(metrics)) {
      continue;
    }

    for (const metric of metrics) {
      const name = metric.name as string | undefined;
      if (!name) {
        continue;
      }

      // Extract data points
      const dataPoints = metric.sum?.dataPoints || metric.gauge?.dataPoints || [];
      if (!Array.isArray(dataPoints)) {
        continue;
      }

      for (const dataPoint of dataPoints) {
        const value = dataPoint.value as number | undefined;
        const timestamp = dataPoint.timeUnixNano as number | undefined;
        
        if (value === undefined || timestamp === undefined) {
          continue;
        }

        telemetry.push({
          tenant_id: tenantId,
          timestamp: Math.floor(timestamp / 1000000), // Convert nanoseconds to milliseconds
          metric_name: name,
          metric_value: value,
          tags: dataPoint.attributes as Record<string, string | number> | undefined,
        });
      }
    }
  }

  if (telemetry.length === 0) {
    return null;
  }

  return {
    tenant_id: tenantId,
    telemetry,
  };
}

