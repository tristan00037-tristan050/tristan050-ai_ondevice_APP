#!/usr/bin/env bash
set -euo pipefail

RELEASE_GATE_POLICY_V1_OK=0
RELEASE_GATE_WIRING_V1_OK=0
RELEASE_BLOCKED_WITHOUT_GATES_OK=0

trap 'echo "RELEASE_GATE_POLICY_V1_OK=$RELEASE_GATE_POLICY_V1_OK";
      echo "RELEASE_GATE_WIRING_V1_OK=$RELEASE_GATE_WIRING_V1_OK";
      echo "RELEASE_BLOCKED_WITHOUT_GATES_OK=$RELEASE_BLOCKED_WITHOUT_GATES_OK"' EXIT

policy="docs/ops/contracts/RELEASE_GATE_POLICY_V1.md"
ssot="docs/ops/contracts/RELEASE_WORKFLOWS_V1.txt"

test -f "$policy" || { echo "BLOCK: missing $policy"; exit 1; }
grep -q "RELEASE_GATE_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing token"; exit 1; }
test -s "$ssot" || { echo "BLOCK: missing/empty $ssot"; exit 1; }

RELEASE_GATE_POLICY_V1_OK=1

missing=0
bad=0

while IFS= read -r wf || [ -n "$wf" ]; do
  wf="${wf%%#*}"
  wf="$(echo "$wf" | awk '{$1=$1;print}')"
  [ -z "$wf" ] && continue

  f=".github/workflows/$wf"
  test -f "$f" || { echo "BLOCK: workflow missing: $f"; exit 1; }

  # 1) verify_repo_contracts 호출 강제
  grep -q "scripts/verify/verify_repo_contracts.sh" "$f" || { echo "BLOCK: $wf missing verify_repo_contracts"; missing=1; }

  # 2) autodecision 결과 파일 존재/decision 검사 강제(최소한 grep 수준이라도 워크플로에 있어야 함)
  #    (정확한 파싱은 워크플로 단계에서 node로 수행해도 됨)
  grep -Eq "autodecision_latest\.json" "$f" || { echo "BLOCK: $wf missing autodecision file check"; missing=1; }

  # 3) autodecision decision==ok 검사 강제 (문자열 존재만으로는 부족)
  #    decision 비교가 실제로 있어야 함 (ok 비교 or not-ok BLOCK)
  grep -Eq 'decision.*"ok"|decision!==\"ok\"|decision!=\=\"ok\"' "$f" || {
    echo "BLOCK: $wf missing autodecision decision==ok enforcement"
    missing=1
  }

  # 4) 게이트 없는 릴리즈 방지: 'continue-on-error: true'로 verify를 무력화하면 안 됨
  grep -Eq "continue-on-error:[[:space:]]*true" "$f" && { echo "BLOCK: $wf has continue-on-error true (bypass risk)"; bad=1; }

  # 5) release 시 strict proof 필수: env 제거 시 즉시 BLOCK
  grep -Eq 'ONPREM_PROOF_STRICT_ENFORCE:[[:space:]]*"1"' "$f" || {
    echo "BLOCK: $wf missing ONPREM_PROOF_STRICT_ENFORCE=1 for release"
    missing=1
  }
done < "$ssot"

[ "$missing" -eq 0 ] || exit 1
[ "$bad" -eq 0 ] || exit 1

RELEASE_GATE_WIRING_V1_OK=1
RELEASE_BLOCKED_WITHOUT_GATES_OK=1
exit 0
