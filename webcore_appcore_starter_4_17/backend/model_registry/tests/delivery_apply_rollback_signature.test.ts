import { describe, it, expect, beforeEach } from "@jest/globals";
import { getDelivery, createModel, createModelVersion, createArtifact, releaseModelVersion, setReleasePointer, initializeSigningKey } from "../services/storage";
import { applyArtifact, rollbackArtifact } from "../services/delivery";

// Note: clearAll is not exported from services/storage, so we'll create test data fresh each time

/**
 * P0-6: delivery/apply/rollback signature enforcement (deny-by-default)
 * NOTE: 이 테스트는 "서명/만료/키" 검증 실패 시 apply/rollback이 0으로 막히는지를 봉인한다.
 */

describe("SVR-03 signed delivery/apply/rollback (deny-by-default)", () => {
  beforeEach(() => {
    // Initialize signing key for each test
    initializeSigningKey();
  });

  it("[EVID:MODEL_DELIVERY_SIGNATURE_REQUIRED_OK] delivery includes signature fields", async () => {
    const model = createModel("tenant1", "user1", { name: "test-model" });
    const version = createModelVersion(model.id, "tenant1", "user1", { version: "1.0.0" });
    const artifact = createArtifact(version.id, "tenant1", "user1", {
      platform: "android",
      runtime: "tflite",
      sha256: "abc123",
      file_size: 1024,
      file_path: "s3://bucket/key",
      model_id: model.id,
      version: version.version,
    });
    releaseModelVersion(version.id, "tenant1", "user1");
    setReleasePointer(model.id, "tenant1", "user1", {
      platform: "android",
      runtime: "tflite",
      model_version_id: version.id,
      artifact_id: artifact.id,
    });

    const delivery = getDelivery(model.id, "tenant1", "android", "tflite");

    expect(delivery).not.toBeNull();
    expect(delivery!.sha256).toBeTruthy();
    expect(delivery!.signature).toBeTruthy();
    expect(delivery!.key_id).toBeTruthy();
    expect(typeof delivery!.ts_ms).toBe("number");
    expect(typeof delivery!.expires_at).toBe("number");
  });

  it("[EVID:MODEL_APPLY_FAILCLOSED_OK] apply fails closed on missing/invalid/expired signature", async () => {
    const model = createModel("tenant1", "user1", { name: "test-model" });
    const version = createModelVersion(model.id, "tenant1", "user1", { version: "1.0.0" });
    const artifact = createArtifact(version.id, "tenant1", "user1", {
      platform: "android",
      runtime: "tflite",
      sha256: "abc123",
      file_size: 1024,
      file_path: "s3://bucket/key",
      model_id: model.id,
      version: version.version,
    });
    releaseModelVersion(version.id, "tenant1", "user1");
    setReleasePointer(model.id, "tenant1", "user1", {
      platform: "android",
      runtime: "tflite",
      model_version_id: version.id,
      artifact_id: artifact.id,
    });

    const delivery = getDelivery(model.id, "tenant1", "android", "tflite");
    expect(delivery).not.toBeNull();

    // Case 1: Missing signature
    const r1 = applyArtifact("tenant1", {
      sha256: delivery!.sha256,
      model_id: model.id,
      version_id: version.id,
      artifact_id: artifact.id,
      // signature, key_id missing
    });
    expect(r1.ok).toBe(false);
    expect(r1.applied).toBe(false);
    expect("reason_code" in r1 && r1.reason_code).toBe("SIGNATURE_MISSING");

    // Case 2: Invalid signature (tampered sha256)
    const tampered = {
      ...delivery!,
      sha256: delivery!.sha256.replace(/./, "0"), // Tamper sha256
    };
    const r2 = applyArtifact("tenant1", {
      ...tampered,
      model_id: model.id,
      version_id: version.id,
      artifact_id: artifact.id,
    });
    expect(r2.ok).toBe(false);
    expect(r2.applied).toBe(false);
    expect("reason_code" in r2 && r2.reason_code).toBeDefined();

    // Case 3: Expired signature
    const expired = {
      ...delivery!,
      expires_at: 1, // Past expiration
    };
    const r3 = applyArtifact("tenant1", {
      ...expired,
      model_id: model.id,
      version_id: version.id,
      artifact_id: artifact.id,
    });
    expect(r3.ok).toBe(false);
    expect(r3.applied).toBe(false);
    expect("reason_code" in r3 && r3.reason_code).toBe("SIGNATURE_EXPIRED");
  });

  it("[EVID:MODEL_ROLLBACK_OK] rollback is safe (fail-closed on invalid signature)", async () => {
    const model = createModel("tenant1", "user1", { name: "test-model" });
    const version = createModelVersion(model.id, "tenant1", "user1", { version: "1.0.0" });
    const artifact = createArtifact(version.id, "tenant1", "user1", {
      platform: "android",
      runtime: "tflite",
      sha256: "abc123",
      file_size: 1024,
      file_path: "s3://bucket/key",
      model_id: model.id,
      version: version.version,
    });
    releaseModelVersion(version.id, "tenant1", "user1");
    setReleasePointer(model.id, "tenant1", "user1", {
      platform: "android",
      runtime: "tflite",
      model_version_id: version.id,
      artifact_id: artifact.id,
    });

    const delivery = getDelivery(model.id, "tenant1", "android", "tflite");
    expect(delivery).not.toBeNull();

    // Missing signature
    const r = rollbackArtifact("tenant1", {
      sha256: delivery!.sha256,
      model_id: model.id,
      version_id: version.id,
      artifact_id: artifact.id,
      reason_code: "TEST_ROLLBACK",
      // signature, key_id missing
    });
    expect(r.ok).toBe(false);
    expect(r.rolled_back).toBe(false);
    expect("reason_code" in r && r.reason_code).toBe("SIGNATURE_MISSING");
  });
});

