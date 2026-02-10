#!/usr/bin/env bash
set -euo pipefail

# P2-AI-01: On-Device Inference v0 Verification
# 목적: 모델팩 로드 + 추론 + pack params 영향 증명 (4케이스: A/B/C/D)
# Gateway 서버 없이 직접 함수 호출 방식

ONDEVICE_MODEL_PACK_LOADED_OK=0
ONDEVICE_MODEL_PACK_IDENTITY_OK=0
ONDEVICE_INFERENCE_ONCE_OK=0
ONDEVICE_OUTPUT_FINGERPRINT_OK=0
ONDEVICE_INFER_USES_PACK_PARAMS_OK=0

cleanup() {
  echo "ONDEVICE_MODEL_PACK_LOADED_OK=${ONDEVICE_MODEL_PACK_LOADED_OK}"
  echo "ONDEVICE_MODEL_PACK_IDENTITY_OK=${ONDEVICE_MODEL_PACK_IDENTITY_OK}"
  echo "ONDEVICE_INFERENCE_ONCE_OK=${ONDEVICE_INFERENCE_ONCE_OK}"
  echo "ONDEVICE_OUTPUT_FINGERPRINT_OK=${ONDEVICE_OUTPUT_FINGERPRINT_OK}"
  echo "ONDEVICE_INFER_USES_PACK_PARAMS_OK=${ONDEVICE_INFER_USES_PACK_PARAMS_OK}"
  if [[ "$ONDEVICE_MODEL_PACK_LOADED_OK" == "1" ]] && \
     [[ "$ONDEVICE_MODEL_PACK_IDENTITY_OK" == "1" ]] && \
     [[ "$ONDEVICE_INFERENCE_ONCE_OK" == "1" ]] && \
     [[ "$ONDEVICE_OUTPUT_FINGERPRINT_OK" == "1" ]] && \
     [[ "$ONDEVICE_INFER_USES_PACK_PARAMS_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

# Node 18+ 확인 (ESM import 필요)
node -e 'process.exit((parseInt(process.versions.node.split(".")[0],10) >= 18) ? 0 : 1)' \
  || { echo "ERROR_CODE=NODE_VERSION_INSUFFICIENT"; echo "BLOCK: Node 18+ required (install forbidden)"; exit 1; }

# 임시 디렉터리
TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR" || true
}

# 통합 cleanup (tmp 정리 + DoD 키 출력)
on_exit() {
  cleanup_tmp
  cleanup
}
trap on_exit EXIT

# CommonJS 테스트 러너 (직접 함수 호출, Gateway 없음)
cat > "$TMP_DIR/inference_runner.cjs" <<'RUNNER'
const { createRequire } = require("module");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");

const ROOT = process.argv[2];

function sha256(s) {
  return crypto.createHash("sha256").update(String(s ?? ""), "utf8").digest("hex");
}

// ESM 모듈 동적 import (Node 18+)
// dist 폴더의 컴파일된 JavaScript 사용 (TypeScript 직접 import 불가)
async function importESM(modulePath) {
  // src/lib/osAlgoCore.ts -> dist/lib/osAlgoCore.js
  const jsPath = modulePath.replace(/\/src\//, "/dist/").replace(/\.ts$/, ".js");
  const fullPath = path.resolve(ROOT, jsPath);
  
  if (!fs.existsSync(fullPath)) {
    const err = new Error("MODULE_NOT_FOUND");
    err.code = `MODULE_NOT_FOUND: ${jsPath}`;
    throw err;
  }
  
  // file:// URL로 변환 (경로에 공백/특수문자 처리)
  const fileUrl = `file://${fullPath}`;
  return await import(fileUrl);
}

async function callGenerateThreeBlocks(modelId, intent) {
  try {
    // 직접 import (Gateway 없이, dist 폴더 사용)
    const osAlgoCore = await importESM("webcore_appcore_starter_4_17/packages/bff-accounting/src/lib/osAlgoCore.ts");
    
    const metaReq = {
      request_id: `test_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      intent: intent || "업무일지",
      model_id: modelId,
      device_class: "demo",
      client_version: "1.0.0",
      ts_utc: new Date().toISOString()
    };

    const blocks = await osAlgoCore.generateThreeBlocks(metaReq);
    
    // pack meta 추출
    const packMeta = blocks.__pack_meta || {};
    delete blocks.__pack_meta;
    
    return {
      ok: true,
      blocks,
      pack_id: packMeta.pack_id || null,
      version: packMeta.pack_version || null,
      manifest_sha256: packMeta.manifest_sha256 || null,
      result_fingerprint_sha256: packMeta.result_fingerprint_sha256 || null,
      compute_path: packMeta.compute_path || null,
    };
  } catch (e) {
    // code-only (e.message 금지)
    const code = e?.code || "INFER_FAILED";
    return {
      ok: false,
      error_code: code,
      result_fingerprint_sha256: null,
      pack_id: null,
    };
  }
}

// 케이스 A: good pack → infer OK
async function testCaseA() {
  const result = await callGenerateThreeBlocks("demoA", "업무일지");
  if (!result.ok) {
    const err = new Error("CASE_A_FAILED");
    err.code = result.error_code || "CASE_A_FAILED";
    throw err;
  }
  if (!result.result_fingerprint_sha256) {
    const err = new Error("CASE_A_FAILED");
    err.code = "CASE_A_FAILED_FINGERPRINT_MISSING";
    throw err;
  }
  if (!result.pack_id || result.pack_id !== "demoA") {
    const err = new Error("CASE_A_FAILED");
    err.code = "CASE_A_FAILED_PACK_ID_MISMATCH";
    throw err;
  }
  return {
    case: "A",
    ok: true,
    pack_id: result.pack_id,
    version: result.version,
    manifest_sha256: result.manifest_sha256,
    result_fingerprint_sha256: result.result_fingerprint_sha256,
    compute_path: result.compute_path,
  };
}

// 케이스 B: bad pack → apply=0 + infer BLOCK (negative-first)
async function testCaseB() {
  // bad pack: 존재하지 않는 pack_id
  const result = await callGenerateThreeBlocks("_bad_pack_not_found", "업무일지");
  if (result.ok) {
    const err = new Error("CASE_B_FAILED");
    err.code = "CASE_B_FAILED_BAD_PACK_SHOULD_BE_BLOCKED";
    throw err;
  }
  if (!result.error_code || !result.error_code.includes("PACK_")) {
    const err = new Error("CASE_B_FAILED");
    err.code = "CASE_B_FAILED_WRONG_ERROR_CODE";
    throw err;
  }
  return {
    case: "B",
    ok: false,
    error_code: result.error_code,
    blocked: true,
  };
}

// 케이스 C: pack params 영향 증명 (가장 중요)
async function testCaseC() {
  const resultA = await callGenerateThreeBlocks("demoA", "업무일지");
  const resultB = await callGenerateThreeBlocks("demoB", "업무일지");
  
  if (!resultA.ok || !resultB.ok) {
    const err = new Error("CASE_C_FAILED");
    err.code = `CASE_C_FAILED_BOTH_MUST_SUCCEED_A_${resultA.error_code}_B_${resultB.error_code}`;
    throw err;
  }
  
  const fpA = resultA.result_fingerprint_sha256;
  const fpB = resultB.result_fingerprint_sha256;
  
  if (!fpA || !fpB) {
    const err = new Error("CASE_C_FAILED");
    err.code = "CASE_C_FAILED_FINGERPRINTS_MISSING";
    throw err;
  }
  
  if (fpA === fpB) {
    const err = new Error("CASE_C_FAILED");
    err.code = "CASE_C_FAILED_FINGERPRINTS_MUST_DIFFER";
    throw err;
  }
  
  return {
    case: "C",
    ok: true,
    demoA_fingerprint: fpA,
    demoB_fingerprint: fpB,
    fingerprints_differ: true,
  };
}

// 케이스 D: meta-only 위반 차단 (no-raw negative)
async function testCaseD() {
  try {
    // 금지 키 포함 payload 시도
    // 직접 import (Gateway 없이, dist 폴더 사용)
    const osAlgoCore = await importESM("webcore_appcore_starter_4_17/packages/bff-accounting/src/lib/osAlgoCore.ts");
    
    const metaReq = {
      request_id: `test_${Date.now()}`,
      intent: "업무일지",
      model_id: "demoA",
      device_class: "demo",
      client_version: "1.0.0",
      ts_utc: new Date().toISOString(),
      prompt: "금지된 키", // 금지 키
    };

    // validateMetaOnlyOrThrow가 에러를 던져야 함
    try {
      osAlgoCore.validateMetaOnlyOrThrow(metaReq);
      // 에러가 안 나면 실패
      const err = new Error("CASE_D_FAILED");
      err.code = "CASE_D_FAILED_FORBIDDEN_KEY_NOT_BLOCKED";
      throw err;
    } catch (e) {
      // META_ONLY_* 에러 코드 확인
      if (!e?.message || !e.message.includes("META_ONLY_")) {
        const err = new Error("CASE_D_FAILED");
        err.code = "CASE_D_FAILED_WRONG_ERROR_CODE";
        throw err;
      }
    }
    
    return {
      case: "D",
      ok: false,
      error_code: "META_ONLY_VIOLATION",
      blocked: true,
    };
  } catch (e) {
    if (e.message && e.message.includes("CASE_D_FAILED")) {
      throw e;
    }
    // code-only (e.message 금지)
    const err = new Error("CASE_D_FAILED");
    err.code = e?.code || "CASE_D_FAILED";
    throw err;
  }
}

async function main() {
  const results = [];
  
  try {
    const caseA = await testCaseA();
    results.push(caseA);
    console.error(JSON.stringify({ reason_code: "CASE_A_PASS", ...caseA }));
  } catch (e) {
    // code-only (e.message 금지)
    const code = e?.code || "CASE_A_FAIL";
    console.error(JSON.stringify({ reason_code: "CASE_A_FAIL", error_code: code }));
    process.exit(1);
  }
  
  try {
    const caseB = await testCaseB();
    results.push(caseB);
    console.error(JSON.stringify({ reason_code: "CASE_B_PASS", ...caseB }));
  } catch (e) {
    // code-only (e.message 금지)
    const code = e?.code || "CASE_B_FAIL";
    console.error(JSON.stringify({ reason_code: "CASE_B_FAIL", error_code: code }));
    process.exit(1);
  }

  try {
    const caseC = await testCaseC();
    results.push(caseC);
    console.error(JSON.stringify({ reason_code: "CASE_C_PASS", ...caseC }));
  } catch (e) {
    // code-only (e.message 금지)
    const code = e?.code || "CASE_C_FAIL";
    console.error(JSON.stringify({ reason_code: "CASE_C_FAIL", error_code: code }));
    process.exit(1);
  }

  try {
    const caseD = await testCaseD();
    results.push(caseD);
    console.error(JSON.stringify({ reason_code: "CASE_D_PASS", ...caseD }));
  } catch (e) {
    // code-only (e.message 금지)
    const code = e?.code || "CASE_D_FAIL";
    console.error(JSON.stringify({ reason_code: "CASE_D_FAIL", error_code: code }));
    process.exit(1);
  }

  // 최종 출력 (meta-only)
  console.log(JSON.stringify({
    reason_code: "P2_AI_01_INFERENCE_VERIFIED",
    cases: results.map(r => ({
      case: r.case,
      ok: r.ok,
      pack_id: r.pack_id || null,
      result_fingerprint_sha256: r.result_fingerprint_sha256 || r.demoA_fingerprint?.slice(0, 8) || null,
      error_code: r.error_code || null,
    }))
  }));
}

main().catch(e => {
  // code-only (e.message 금지)
  const code = e?.code || "RUNNER_FAILED";
  console.error(JSON.stringify({ reason_code: "RUNNER_FAILED", error_code: code }));
  process.exit(1);
});
RUNNER

# Node.js 러너 실행 (빌드/설치/네트워크 금지, 판정만)
# Gateway 없이 직접 함수 호출

# 러너 실행
RUNNER_OUTPUT="$(node "$TMP_DIR/inference_runner.cjs" "$ROOT" 2>&1)"
RUNNER_RC=$?

if [[ "$RUNNER_RC" -ne 0 ]]; then
  echo "BLOCK: inference runner failed"
  echo "$RUNNER_OUTPUT" | tail -5
  exit 1
fi

# 결과 파싱 (meta-only)
FINAL_RESULT="$(echo "$RUNNER_OUTPUT" | grep -E "P2_AI_01_INFERENCE_VERIFIED" | head -1 || echo "")"
if [[ -z "$FINAL_RESULT" ]]; then
  echo "BLOCK: final result not found"
  echo "$RUNNER_OUTPUT" | tail -10
  exit 1
fi

# 케이스별 검증
CASE_A_PASS="$(echo "$RUNNER_OUTPUT" | grep -c "CASE_A_PASS" || echo "0")"
CASE_B_PASS="$(echo "$RUNNER_OUTPUT" | grep -c "CASE_B_PASS" || echo "0")"
CASE_C_PASS="$(echo "$RUNNER_OUTPUT" | grep -c "CASE_C_PASS" || echo "0")"
CASE_D_PASS="$(echo "$RUNNER_OUTPUT" | grep -c "CASE_D_PASS" || echo "0")"

if [[ "$CASE_A_PASS" -eq 0 ]]; then
  echo "BLOCK: CASE_A failed (good pack infer)"
  exit 1
fi
ONDEVICE_MODEL_PACK_LOADED_OK=1
ONDEVICE_INFERENCE_ONCE_OK=1

if [[ "$CASE_B_PASS" -eq 0 ]]; then
  echo "BLOCK: CASE_B failed (bad pack block)"
  exit 1
fi

if [[ "$CASE_C_PASS" -eq 0 ]]; then
  echo "BLOCK: CASE_C failed (pack params affect fingerprint)"
  exit 1
fi
ONDEVICE_INFER_USES_PACK_PARAMS_OK=1
ONDEVICE_OUTPUT_FINGERPRINT_OK=1

if [[ "$CASE_D_PASS" -eq 0 ]]; then
  echo "BLOCK: CASE_D failed (meta-only violation block)"
  exit 1
fi

# pack identity 검증 (pack_id/version/manifest_sha256 파싱 가능)
CASE_A_JSON="$(echo "$RUNNER_OUTPUT" | grep "CASE_A_PASS" | head -1)"
if echo "$CASE_A_JSON" | grep -q '"pack_id":"demoA"'; then
  if echo "$CASE_A_JSON" | grep -q '"version"'; then
    if echo "$CASE_A_JSON" | grep -q '"manifest_sha256"'; then
      ONDEVICE_MODEL_PACK_IDENTITY_OK=1
    fi
  fi
fi

if [[ "$ONDEVICE_MODEL_PACK_IDENTITY_OK" -eq 0 ]]; then
  echo "BLOCK: pack identity fields missing (pack_id/version/manifest_sha256)"
  exit 1
fi

# cleanup 함수가 DoD 키를 출력하고 exit 처리
# (명시적 exit 0 제거, cleanup이 처리)
