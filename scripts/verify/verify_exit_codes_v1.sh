#!/usr/bin/env bash
set -euo pipefail

VERIFY_EXIT_CODES_V1_OK=0
trap 'echo "VERIFY_EXIT_CODES_V1_OK=${VERIFY_EXIT_CODES_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/VERIFY_EXIT_CODES_V1.txt"
[[ -f "$SSOT" ]] || { echo "ERROR_CODE=VERIFY_EXIT_CODES_SSOT_MISSING"; exit 1; }
grep -q '^VERIFY_EXIT_CODES_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=VERIFY_EXIT_CODES_TOKEN_MISSING"; exit 1; }

# P22-P1-FINAL: 신규 exit code 존재 확인
grep -q '^EXIT_ARGS_INVALID=15' "$SSOT" || { echo "ERROR_CODE=VERIFY_EXIT_CODES_ARGS_INVALID_MISSING"; exit 1; }
grep -q '^EXIT_CHAIN_ORDER_INVALID=16' "$SSOT" || { echo "ERROR_CODE=VERIFY_EXIT_CODES_CHAIN_ORDER_INVALID_MISSING"; exit 1; }

# P22-P1-FINAL: node_args_v1.cjs 에서 숫자 리터럴 process.exit 금지 확인
RUNTIME_NODE_ARGS="tools/verify-runtime/node_args_v1.cjs"
[[ -f "$ROOT/$RUNTIME_NODE_ARGS" ]] || { echo "ERROR_CODE=VERIFY_EXIT_CODES_RUNTIME_MISSING"; exit 1; }
if grep -nE 'process\.exit\(([1-9][0-9]*)\)' "$ROOT/$RUNTIME_NODE_ARGS" 2>/dev/null | grep -qv 'EXIT\.'; then
  echo "ERROR_CODE=VERIFY_EXIT_CODES_LITERAL_FOUND_IN_RUNTIME"
  exit 1
fi

# 이번 단계에서 EXIT registry 사용 대상 verifier만 검사 (점진적 확대)
# 0이 아닌 숫자 리터럴만 차단 (process.exit(0) 은 성공)
SCOPE_FILES=(
  scripts/verify/verify_sbom_from_artifacts_v1.sh
  scripts/verify/verify_artifact_bundle_integrity_v1.sh
  scripts/verify/verify_artifact_bundle_provenance_link_v1.sh
)
HIT="$(for f in "${SCOPE_FILES[@]}"; do [[ -f "$ROOT/$f" ]] && grep -nE 'process\.exit\(([1-9][0-9]*)\)' "$ROOT/$f" 2>/dev/null || true; done || true)"
if [[ -n "$HIT" ]]; then
  echo "ERROR_CODE=VERIFY_EXIT_CODES_LITERAL_FOUND"
  echo "HIT_PATH=$(printf '%s\n' "$HIT" | head -n1 | cut -d: -f1)"
  exit 1
fi

VERIFY_EXIT_CODES_V1_OK=1
exit 0
