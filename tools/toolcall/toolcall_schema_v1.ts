'use strict';

// P23-P1-03: GUIDED_TOOLCALL_SCHEMA_V1
// Schema-constrained tool call contract. Unconstrained JSON tool calls are forbidden.

import { typedDigest } from '../crypto/digest_v1';

export interface ToolSchema {
  tool_id: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
}

export interface GuidedToolCallContract {
  pack_id: string;
  tool_schema_digest_sha256: string;
  guided_generation_schema_digest_sha256: string;
  tool_policy_digest_sha256: string;
}

export function buildToolSchemaDigest(schema: ToolSchema): string {
  return typedDigest('tool-schema', 'v1', schema);
}

export function assertGuidedToolCallContract(c: unknown): asserts c is GuidedToolCallContract {
  if (!c || typeof c !== 'object') {
    throw new TypeError('GuidedToolCallContract must be a non-null object');
  }
  const required = [
    'pack_id',
    'tool_schema_digest_sha256',
    'guided_generation_schema_digest_sha256',
    'tool_policy_digest_sha256',
  ];
  for (const k of required) {
    if (!(c as Record<string, unknown>)[k]) {
      throw new Error(`TOOLCALL_CONTRACT_MISSING:${k}`);
    }
  }
}
