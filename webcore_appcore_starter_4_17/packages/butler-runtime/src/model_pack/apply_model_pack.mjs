// webcore_appcore_starter_4_17/packages/butler-runtime/src/model_pack/apply_model_pack.mjs
import { readState, writeStateAtomicDurable } from "./state_store.mjs";

// TS SSOT에서 reason codes를 로드(중복 정의 금지)
import { assertReasonCodeV1 } from "../../../../../packages/common/src/reason_codes/reason_codes_v1_data.mjs";

export function applyModelPackOrBlock(args) {
  const before = readState(args.state_path);

  // 1) 검증 실패 => 상태 불변 + reason_code 보존
  if (!args.verified) {
    const rc = assertReasonCodeV1(args.verify_reason_code);
    return {
      applied: false,
      reason_code: rc,
      active_pack_id: before.active_pack_id,
      active_manifest_sha256: before.active_manifest_sha256,
    };
  }

  // 2) 만료 검증 fail-closed (상태 불변)
  if (!Number.isFinite(args.expires_at_ms) || args.expires_at_ms <= 0) {
    return { applied: false, reason_code: "EXPIRES_AT_INVALID", ...before };
  }
  if (args.now_ms > args.expires_at_ms) {
    return { applied: false, reason_code: "EXPIRED_BLOCKED", ...before };
  }

  // 3) 적용 성공 => 상태 갱신(원자/내구성)
  const next = {
    active_pack_id: args.pack_id,
    active_manifest_sha256: args.manifest_sha256,
    updated_utc: new Date(args.now_ms).toISOString(),
  };

  writeStateAtomicDurable(args.state_path, next);

  return {
    applied: true,
    reason_code: "APPLY_OK",
    active_pack_id: next.active_pack_id,
    active_manifest_sha256: next.active_manifest_sha256,
  };
}

