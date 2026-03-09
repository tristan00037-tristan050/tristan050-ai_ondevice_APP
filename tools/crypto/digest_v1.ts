'use strict';

// P23-P0A-05: DIGEST_CANONICAL_AND_DOMAIN_TAG_V1
// Domain-tagged, schema-versioned digest utility.
// JCS canonicalization sourced from packages/common/src/crypto/jcs.ts (single source).

import crypto from 'node:crypto';
import { jcsCanonicalize } from '../../packages/common/src/crypto/jcs.js';

function sha256Hex(s: string): string {
  return crypto.createHash('sha256').update(s, 'utf8').digest('hex');
}

export function typedDigest<T>(domainTag: string, schemaVersion: string, payload: T): string {
  const canonical = jcsCanonicalize({
    domain_tag: domainTag,
    schema_version: schemaVersion,
    payload,
  });
  return sha256Hex(canonical);
}

export function routingDecisionDigest(input: {
  pack_id: string;
  reason_code: string;
  profile_snapshot: Record<string, unknown> | null;
  policy_version: string;
  schema_version: number;
}): string {
  return typedDigest('routing-decision', 'v1', input);
}

export function routingEventId(input: {
  timestamp_ns: string;
  pack_id: string;
  reason_code: string;
  profile_snapshot: Record<string, unknown> | null;
  policy_version: string;
  schema_version: number;
}): string {
  return typedDigest('routing-event', 'v1', input);
}
