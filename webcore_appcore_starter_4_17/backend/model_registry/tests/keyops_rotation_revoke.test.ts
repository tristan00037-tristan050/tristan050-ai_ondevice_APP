import { describe, it, expect, beforeEach } from "@jest/globals";
import { upsertKey, canVerifyWithKey } from "../services/key_store";

describe("SVR-03 key ops: rotation + revoke (fail-closed)", () => {
  beforeEach(() => {
    // in-memory store라면 테스트 간 초기화가 필요할 수 있습니다.
    // 현재 구현이 Map을 모듈 스코프로 두었으므로, 이 테스트에서는 key_id를 매번 다르게 사용합니다.
  });

  it("[EVID:KEY_ROTATION_MULTIKEY_VERIFY_OK] multi-key verify allowed during grace", () => {
    const now = Date.now();
    upsertKey({ key_id: "k_old", public_key_pem: "PEM_OLD", state: "grace", grace_until_ms: now + 60_000 });
    upsertKey({ key_id: "k_new", public_key_pem: "PEM_NEW", state: "active" });

    expect(canVerifyWithKey("k_new", now).ok).toBe(true);
    expect(canVerifyWithKey("k_old", now).ok).toBe(true);
  });

  it("[EVID:KEY_REVOCATION_BLOCK_OK] revoked key must be blocked immediately", () => {
    const now = Date.now();
    upsertKey({ key_id: "k_rev", public_key_pem: "PEM_REV", state: "revoked" });

    const r = canVerifyWithKey("k_rev", now);
    expect(r.ok).toBe(false);
    expect(r.reason_code).toBe("KEY_REVOKED");
  });

  it("[EVID:KEY_ROTATION_GRACE_PERIOD_OK] grace expired must be blocked", () => {
    const now = Date.now();
    upsertKey({ key_id: "k_grace", public_key_pem: "PEM_G", state: "grace", grace_until_ms: now - 1 });

    const r = canVerifyWithKey("k_grace", now);
    expect(r.ok).toBe(false);
    expect(r.reason_code).toBe("KEY_GRACE_EXPIRED");
  });
});

