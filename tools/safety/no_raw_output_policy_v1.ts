'use strict';

// AI-P3-SAFETY: NO_RAW_OUTPUT_POLICY_V1
// digest-only logging 원칙 전사 적용.
// logs / exceptions / reports / proofs 전 경로에서 raw 원문 출력 차단.

import { createHash } from 'node:crypto';

export const NO_RAW_POLICY_VERSION = 'v1';

// raw 출력 금지 패턴 (정적 분석용)
export const RAW_LEAK_PATTERNS = [
  /logger\.(info|warn|error|debug)\s*\(.*\$\{.*(prompt|output|input|response)/i,
  /console\.(log|warn|error)\s*\(.*\$\{.*(prompt|output|input|response)/i,
  /throw new Error\s*\(.*\$\{.*(prompt|output|input|response)/i,
  /JSON\.stringify\s*\(.*prompt/i,
  /JSON\.stringify\s*\(.*output/i,
];

/**
 * Compute SHA-256 hex digest of an input string.
 * Used internally by all safe logging/throwing helpers.
 */
export function computeSha256Hex(input: string): string {
  return createHash('sha256').update(input, 'utf8').digest('hex');
}

/**
 * Log only the SHA-256 digest of a raw value — never the raw value itself.
 * Enforces digest-only logging at call site.
 */
export function safeLogDigestOnly(
  logger: { info: (msg: string) => void },
  label: string,
  raw: string
): void {
  const digest = computeSha256Hex(raw);
  logger.info(`${label}_digest=${digest}`);
}

/**
 * Throw an Error that includes only the SHA-256 digest of the offending value.
 * Raw content is never included in the thrown message.
 */
export function throwSafeError(
  code: string,
  raw: string
): never {
  const digest = computeSha256Hex(raw);
  throw new Error(`${code}:digest=${digest}`);
}

/**
 * Assert that a string field does not contain raw content.
 * Rejects strings longer than 200 chars that are not a 64-char hex digest.
 * @throws Error('NO_RAW_POLICY_VIOLATION:...') on violation.
 */
export function assertNoRawInString(
  value: string,
  fieldName: string
): void {
  if (value.length > 200 && !/^[0-9a-f]{64}$/.test(value)) {
    throw new Error(`NO_RAW_POLICY_VIOLATION:${fieldName}:length=${value.length}`);
  }
}
