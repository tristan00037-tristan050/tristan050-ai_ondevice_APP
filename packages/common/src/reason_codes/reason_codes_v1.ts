// packages/common/src/reason_codes/reason_codes_v1.ts
export const REASON_CODES_V1_VERSION = "v1" as const;

export const REASON_CODES_V1 = [
  "META_ONLY_INVALID",
  "EGRESS_DENY_DEFAULT",
  "SIGNATURE_MISSING",
  "SIGNATURE_INVALID",
  "HASH_MISMATCH",
  "MANIFEST_MISSING",
  "MANIFEST_SCHEMA_INVALID",
  "EXPIRES_AT_INVALID",
  "EXPIRED_BLOCKED",
  "APPLY_BLOCKED",
  "APPLY_OK",
  "AUDIT_EVENT_V2_WRITE_FAILED",
  "AUDIT_EVENT_V2_WRITTEN",
  "REASON_CODE_UNKNOWN_BLOCKED",
  "MODEL_PACK_COMPAT_MISSING",
  "MODEL_PACK_COMPAT_SEMVER_INVALID",
  "MODEL_PACK_COMPAT_RUNTIME_TOO_LOW",
  "MODEL_PACK_COMPAT_GATEWAY_TOO_LOW",
] as const;

export type ReasonCodeV1 = (typeof REASON_CODES_V1)[number];

const SET = new Set<string>(REASON_CODES_V1 as readonly string[]);

export function isReasonCodeV1(x: string): x is ReasonCodeV1 {
  return SET.has(x);
}

export function assertReasonCodeV1(x: string): ReasonCodeV1 {
  if (!SET.has(x)) throw new Error(`REASON_CODE_INVALID:${x}`);
  return x as ReasonCodeV1;
}

