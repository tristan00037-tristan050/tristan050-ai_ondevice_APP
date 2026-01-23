export type KeyState = "active" | "grace" | "revoked";

export type KeyRecord = {
  key_id: string;
  public_key_pem: string;   // verify 용
  state: KeyState;
  grace_until_ms?: number;  // grace 상태일 때만 사용
};

const store = new Map<string, KeyRecord>();

export function upsertKey(rec: KeyRecord) {
  store.set(rec.key_id, rec);
}

export function getKey(key_id: string): KeyRecord | null {
  return store.get(key_id) ?? null;
}

export function canVerifyWithKey(key_id: string, now_ms: number): { ok: boolean; reason_code?: string } {
  const rec = getKey(key_id);
  if (!rec) return { ok: false, reason_code: "KEY_UNKNOWN" };
  if (rec.state === "revoked") return { ok: false, reason_code: "KEY_REVOKED" };
  if (rec.state === "active") return { ok: true };
  // grace
  const until = rec.grace_until_ms ?? 0;
  if (now_ms <= until) return { ok: true };
  return { ok: false, reason_code: "KEY_GRACE_EXPIRED" };
}

