/**
 * Meta-Only Schema Guard
 * Fail-Closed: reject payloads containing raw text, candidate lists, or item-level dumps
 */

export interface MetaOnlyTelemetry {
  tenant_id: string;
  timestamp: number; // Unix timestamp (ms)
  metric_name: string;
  metric_value: number | string; // Number or bucketized string
  tags?: Record<string, string | number>; // Meta-only tags (no raw text)
  metadata?: Record<string, unknown>; // Meta-only metadata
}

export interface IngestRequest {
  tenant_id: string;
  telemetry: MetaOnlyTelemetry[];
}

export type ValidationResult = 
  | { valid: true }
  | { valid: false; reason_code: string; message: string };

/**
 * Check if a value contains raw text (non-meta-only)
 */
function containsRawText(value: unknown): boolean {
  if (typeof value === 'string') {
    // Reject if string is too long (likely raw text)
    if (value.length > 1000) {
      return true;
    }
    // Reject if contains newlines (likely multi-line text)
    if (value.includes('\n')) {
      return true;
    }
    // Reject if contains common text patterns
    if (/[a-z]{20,}/i.test(value)) {
      return true; // Long word sequences
    }
  }
  if (Array.isArray(value)) {
    // Reject arrays with many items (likely candidate lists)
    if (value.length > 100) {
      return true;
    }
    // Check each item
    return value.some(item => containsRawText(item));
  }
  if (typeof value === 'object' && value !== null) {
    // Check object values
    return Object.values(value).some(v => containsRawText(v));
  }
  return false;
}

/**
 * Validate meta-only telemetry
 * Fail-Closed: schema violation => rejected with reason_code
 */
export function validateMetaOnly(telemetry: MetaOnlyTelemetry): ValidationResult {
  // Check required fields
  if (!telemetry.tenant_id || typeof telemetry.tenant_id !== 'string') {
    return {
      valid: false,
      reason_code: 'META_ONLY_MISSING_TENANT_ID',
      message: 'tenant_id is required and must be a string',
    };
  }

  if (!telemetry.metric_name || typeof telemetry.metric_name !== 'string') {
    return {
      valid: false,
      reason_code: 'META_ONLY_MISSING_METRIC_NAME',
      message: 'metric_name is required and must be a string',
    };
  }

  if (telemetry.metric_value === undefined || telemetry.metric_value === null) {
    return {
      valid: false,
      reason_code: 'META_ONLY_MISSING_METRIC_VALUE',
      message: 'metric_value is required',
    };
  }

  // Check metric_value type
  if (typeof telemetry.metric_value !== 'number' && typeof telemetry.metric_value !== 'string') {
    return {
      valid: false,
      reason_code: 'META_ONLY_INVALID_METRIC_VALUE_TYPE',
      message: 'metric_value must be number or string',
    };
  }

  // Check for raw text in metric_value
  if (containsRawText(telemetry.metric_value)) {
    return {
      valid: false,
      reason_code: 'META_ONLY_RAW_TEXT_DETECTED',
      message: 'metric_value contains raw text (not meta-only)',
    };
  }

  // Check tags for raw text
  if (telemetry.tags) {
    if (containsRawText(telemetry.tags)) {
      return {
        valid: false,
        reason_code: 'META_ONLY_RAW_TEXT_IN_TAGS',
        message: 'tags contain raw text (not meta-only)',
      };
    }
  }

  // Check metadata for raw text
  if (telemetry.metadata) {
    if (containsRawText(telemetry.metadata)) {
      return {
        valid: false,
        reason_code: 'META_ONLY_RAW_TEXT_IN_METADATA',
        message: 'metadata contains raw text (not meta-only)',
      };
    }
  }

  // Check for candidate lists (arrays with many items)
  if (telemetry.metadata && Array.isArray(telemetry.metadata)) {
    return {
      valid: false,
      reason_code: 'META_ONLY_CANDIDATE_LIST_DETECTED',
      message: 'metadata contains candidate list (not meta-only)',
    };
  }

  return { valid: true };
}

/**
 * Validate ingest request
 * Fail-Closed: schema violation => rejected with reason_code
 */
export function validateIngestRequest(request: IngestRequest): ValidationResult {
  if (!request.tenant_id || typeof request.tenant_id !== 'string') {
    return {
      valid: false,
      reason_code: 'INGEST_MISSING_TENANT_ID',
      message: 'tenant_id is required',
    };
  }

  if (!Array.isArray(request.telemetry)) {
    return {
      valid: false,
      reason_code: 'INGEST_INVALID_TELEMETRY_ARRAY',
      message: 'telemetry must be an array',
    };
  }

  if (request.telemetry.length === 0) {
    return {
      valid: false,
      reason_code: 'INGEST_EMPTY_TELEMETRY',
      message: 'telemetry array cannot be empty',
    };
  }

  // Validate each telemetry item
  for (let i = 0; i < request.telemetry.length; i++) {
    const item = request.telemetry[i];
    const result = validateMetaOnly(item);
    if (!result.valid) {
      return {
        valid: false,
        reason_code: `${result.reason_code}_AT_INDEX_${i}`,
        message: `${result.message} (at index ${i})`,
      };
    }

    // Ensure tenant_id matches
    if (item.tenant_id !== request.tenant_id) {
      return {
        valid: false,
        reason_code: 'INGEST_TENANT_ID_MISMATCH',
        message: `telemetry item at index ${i} has mismatched tenant_id`,
      };
    }
  }

  return { valid: true };
}

