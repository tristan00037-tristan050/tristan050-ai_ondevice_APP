/**
 * Meta-Only Schema Guard (SDK-side)
 * Fail-Closed: reject payloads containing raw text, identifiers, or candidate lists
 * 
 * APP-04: SDK에서 전송 전 검증하여 서버 부하 감소 및 보안 강화
 */

export interface ValidationResult {
  valid: boolean;
  reason_code?: string;
  message?: string;
}

/**
 * Check if a value contains identifier-like tokens (non-meta-only)
 */
function containsIdentifier(value: unknown): boolean {
  if (typeof value === 'string') {
    const s = value.trim();

    // UUID v4/v1 등
    const uuid =
      /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i;
    if (uuid.test(s)) return true;

    // Long hex tokens (md5/sha1/sha256 등 흔한 길이)
    const hex32 = /\b[0-9a-f]{32}\b/i;
    const hex40 = /\b[0-9a-f]{40}\b/i;
    const hex64 = /\b[0-9a-f]{64}\b/i;
    if (hex32.test(s) || hex40.test(s) || hex64.test(s)) return true;

    // JWT-like (header.payload.signature)
    const jwtLike = /^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$/;
    if (jwtLike.test(s)) return true;

    // High-entropy token-like (base64url-ish) – 보수적으로: 길이>=24, 영문+숫자 혼합
    // 주의: 단순 긴 단어(문장 일부)와 구분하기 위해 숫자 포함을 요구
    if (s.length >= 24 && /^[A-Za-z0-9_-]+$/.test(s) && /[A-Za-z]/.test(s) && /\d/.test(s)) {
      return true;
    }
  }

  if (Array.isArray(value)) {
    return value.some((v) => containsIdentifier(v));
  }

  if (typeof value === 'object' && value !== null) {
    return Object.values(value).some((v) => containsIdentifier(v));
  }

  return false;
}

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
 * Validate telemetry payload for meta-only compliance
 * Fail-Closed: schema violation => rejected with reason_code, never sent
 */
export function validateTelemetryPayload(payload: Record<string, unknown>): ValidationResult {
  // Check all string values for identifiers
  for (const [key, value] of Object.entries(payload)) {
    // Skip known safe fields (enum types, numbers, booleans)
    if (typeof value === 'number' || typeof value === 'boolean') {
      continue;
    }

    // Check string values
    if (typeof value === 'string') {
      // Allow short enum-like strings (eventType, backend, etc.)
      if (key === 'eventType' || key === 'backend') {
        // These are enum types, skip identifier check
        continue;
      }

      // Check for identifiers
      if (containsIdentifier(value)) {
        return {
          valid: false,
          reason_code: 'SDK_META_ONLY_IDENTIFIER_DETECTED',
          message: `Field '${key}' contains identifier-like token (not meta-only)`,
        };
      }

      // Check for raw text
      if (containsRawText(value)) {
        return {
          valid: false,
          reason_code: 'SDK_META_ONLY_RAW_TEXT_DETECTED',
          message: `Field '${key}' contains raw text (not meta-only)`,
        };
      }
    }

    // Check nested objects/arrays
    if (Array.isArray(value)) {
      if (value.length > 100) {
        return {
          valid: false,
          reason_code: 'SDK_META_ONLY_CANDIDATE_LIST_DETECTED',
          message: `Field '${key}' contains candidate list (array with >100 items)`,
        };
      }
      if (containsIdentifier(value) || containsRawText(value)) {
        return {
          valid: false,
          reason_code: 'SDK_META_ONLY_INVALID_ARRAY',
          message: `Field '${key}' contains invalid array content (not meta-only)`,
        };
      }
    }

    if (typeof value === 'object' && value !== null) {
      if (containsIdentifier(value) || containsRawText(value)) {
        return {
          valid: false,
          reason_code: 'SDK_META_ONLY_INVALID_OBJECT',
          message: `Field '${key}' contains invalid object content (not meta-only)`,
        };
      }
    }
  }

  return { valid: true };
}

