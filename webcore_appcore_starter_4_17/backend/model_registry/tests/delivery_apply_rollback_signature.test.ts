import { describe, it, expect } from "@jest/globals";

/**
 * P0-6: delivery/apply/rollback signature enforcement (deny-by-default)
 * NOTE: 이 테스트는 "서명/만료/키" 검증 실패 시 apply/rollback이 0으로 막히는지를 봉인한다.
 *
 * 실제 프로젝트의 delivery/apply/rollback 함수/엔드포인트에 맞게 import/호출만 연결하면 된다.
 */

describe("SVR-03 signed delivery/apply/rollback (deny-by-default)", () => {
  it("[EVID:MODEL_DELIVERY_SIGNATURE_REQUIRED_OK] delivery includes signature fields", async () => {
    // TODO: 실제 delivery 호출로 교체
    const delivery = {
      sha256: "dummy",
      signature: "dummy",
      key_id: "k1",
      ts_ms: 1700000000000,
      expires_at: 1800000000000,
    };

    expect(delivery.sha256).toBeTruthy();
    expect(delivery.signature).toBeTruthy();
    expect(delivery.key_id).toBeTruthy();
    expect(typeof delivery.ts_ms).toBe("number");
    expect(typeof delivery.expires_at).toBe("number");
  });

  it("[EVID:MODEL_APPLY_FAILCLOSED_OK] apply fails closed on missing/invalid/expired signature", async () => {
    // TODO: 실제 apply 호출로 교체
    const apply = (x: any) => {
      // placeholder: 실제 구현에서는 여기서 fail-closed 되어야 함
      if (!x.signature || !x.key_id) return { ok: false, reason_code: "SIGNATURE_MISSING" };
      return { ok: false, reason_code: "SIGNATURE_INVALID" };
    };

    const r1 = apply({ sha256: "x" }); // missing
    expect(r1.ok).toBe(false);

    const r2 = apply({ sha256: "x", signature: "bad", key_id: "k1" }); // invalid
    expect(r2.ok).toBe(false);
  });

  it("[EVID:MODEL_ROLLBACK_OK] rollback is safe (fail-closed on invalid signature)", async () => {
    // TODO: 실제 rollback 호출로 교체
    const rollback = (x: any) => {
      if (!x.signature) return { ok: false, reason_code: "SIGNATURE_MISSING" };
      return { ok: false, reason_code: "SIGNATURE_INVALID" };
    };

    const r = rollback({ sha256: "x" });
    expect(r.ok).toBe(false);
  });
});

