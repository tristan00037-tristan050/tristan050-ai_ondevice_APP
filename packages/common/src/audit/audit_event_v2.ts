export type AuditActorType = "human" | "service" | "system";

export type AuditEventV2 = {
  v: 2;
  ts_utc: string;                 // ISO8601 UTC
  event_id: string;               // unique id (idempotent key)
  actor_type: AuditActorType;
  actor_id_hash: string;          // hashed identifier (no raw PII)
  action: string;                 // e.g., LOCK_FORCE_CLEAR, KEY_REVOKE, KEY_ROTATE
  reason_code: string;            // standardized reason
  repo_sha: string;               // git sha (meta-only)
  target: Record<string, string>; // meta-only target identifiers
  outcome: "ALLOW" | "DENY";
  policy_version: string;         // ssot_ref or policy version
  request_id?: string;            // optional correlation id
};

export function nowUtcIso(): string {
  return new Date().toISOString();
}

