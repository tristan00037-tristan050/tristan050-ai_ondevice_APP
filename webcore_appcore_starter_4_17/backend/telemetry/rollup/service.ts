/**
 * Telemetry Rollup Service
 * Aggregate telemetry data for time-series analysis
 */

import { StoredTelemetry } from '../store/service';
import { queryTelemetry } from '../store/service';

export interface RollupBucket {
  bucket_start: number; // Unix timestamp (ms)
  bucket_end: number;
  metric_name: string;
  count: number;
  sum?: number;
  min?: number;
  max?: number;
  avg?: number;
  tags?: Record<string, string | number>;
}

export interface RollupRequest {
  tenant_id: string;
  metric_name: string;
  start_time: number;
  end_time: number;
  bucket_interval_ms: number; // e.g., 60000 for 1-minute buckets
  tags?: Record<string, string | number>;
}

/**
 * Rollup telemetry into time buckets
 */
export function rollupTelemetry(request: RollupRequest): RollupBucket[] {
  // Query telemetry
  const telemetry = queryTelemetry(request.tenant_id, {
    metric_name: request.metric_name,
    start_time: request.start_time,
    end_time: request.end_time,
    tags: request.tags,
  });

  // Group by time buckets
  const buckets = new Map<number, StoredTelemetry[]>();

  for (const item of telemetry) {
    const bucketStart = Math.floor(item.timestamp / request.bucket_interval_ms) * request.bucket_interval_ms;
    if (!buckets.has(bucketStart)) {
      buckets.set(bucketStart, []);
    }
    buckets.get(bucketStart)!.push(item);
  }

  // Calculate aggregates for each bucket
  const rollupBuckets: RollupBucket[] = [];

  for (const [bucketStart, items] of buckets.entries()) {
    const bucketEnd = bucketStart + request.bucket_interval_ms;
    const numericValues = items
      .map(item => typeof item.metric_value === 'number' ? item.metric_value : null)
      .filter((v): v is number => v !== null);

    const bucket: RollupBucket = {
      bucket_start: bucketStart,
      bucket_end: bucketEnd,
      metric_name: request.metric_name,
      count: items.length,
    };

    if (numericValues.length > 0) {
      bucket.sum = numericValues.reduce((a, b) => a + b, 0);
      bucket.min = Math.min(...numericValues);
      bucket.max = Math.max(...numericValues);
      bucket.avg = bucket.sum / numericValues.length;
    }

    // Preserve tags if all items have the same tags
    if (items.length > 0 && items[0].tags) {
      bucket.tags = items[0].tags;
    }

    rollupBuckets.push(bucket);
  }

  // Sort by bucket_start
  rollupBuckets.sort((a, b) => a.bucket_start - b.bucket_start);

  return rollupBuckets;
}

