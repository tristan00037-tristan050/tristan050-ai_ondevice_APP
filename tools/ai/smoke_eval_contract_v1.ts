'use strict';

export type SmokeType = 'general' | 'guided_toolcall' | 'schema_validator';

export interface SmokeCaseV1 {
  smoke_type: SmokeType;
  prompt_digest_sha256: string;
  expected_schema_id?: string;
}

export interface SmokeRunResultV1 {
  smoke_type: SmokeType;
  prompt_digest_sha256: string;
  output_digest_sha256: string;
  output_length_chars: number;
  pass: boolean;
  reason_code: 'SMOKE_PASS' | 'SMOKE_EMPTY_OUTPUT' | 'SMOKE_ECHO_DETECTED' | 'SMOKE_SCHEMA_FAIL';
}

export function assertSmokeRunResultV1(x: SmokeRunResultV1): void {
  if (x.output_length_chars < 0) {
    throw new Error('SMOKE_OUTPUT_LENGTH_INVALID');
  }
  if (!x.output_digest_sha256 || x.output_digest_sha256.length !== 64) {
    throw new Error('SMOKE_OUTPUT_DIGEST_INVALID');
  }
}
