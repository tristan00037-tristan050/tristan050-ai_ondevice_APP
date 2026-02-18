#!/usr/bin/env bash
set -euo pipefail

EGRESS_DENY_PROOF_HARNESS_V1_OK=0
EGRESS_DENY_RUNBOOK_V1_OK=0
EGRESS_DENY_PROOF_EXECUTES_IN_SANDBOX_OK=0

trap 'echo "EGRESS_DENY_PROOF_HARNESS_V1_OK=${EGRESS_DENY_PROOF_HARNESS_V1_OK}";
      echo "EGRESS_DENY_RUNBOOK_V1_OK=${EGRESS_DENY_RUNBOOK_V1_OK}";
      echo "EGRESS_DENY_PROOF_EXECUTES_IN_SANDBOX_OK=${EGRESS_DENY_PROOF_EXECUTES_IN_SANDBOX_OK}"' EXIT

runbook="tools/egress_proof/RUNBOOK_EGRESS_DENY_PROOF_V1.md"
compose="tools/egress_proof/docker-compose.egress-deny.yml"

test -f "$runbook" || { echo "BLOCK: missing runbook"; exit 1; }
grep -q "EGRESS_DENY_RUNBOOK_V1_TOKEN=1" "$runbook" || { echo "BLOCK: missing runbook token"; exit 1; }
grep -q "EGRESS_DENY_HOST_PROOF_FORBIDDEN=1" "$runbook" || { echo "BLOCK: missing host-proof forbidden token"; exit 1; }
grep -q "EGRESS_DENY_PROOF_MUST_RUN_IN_SANDBOX=1" "$runbook" || { echo "BLOCK: missing sandbox token"; exit 1; }

test -f "$compose" || { echo "BLOCK: missing compose harness"; exit 1; }

# 1) 런북/템플릿에 'host curl로 증빙' 같은 문구/커맨드가 있으면 즉시 BLOCK
#    (금지 문구 설명이 아닌 실제 사용 예시/커맨드만 차단)
#    금지 문구: "금지", "forbidden", "금지한다" 등과 함께 나오면 허용
#    실제 사용: "curl", "wget", "nc" 등이 명령어/예시로 사용되면 차단
if grep -Eqi "(curl|wget|nc).*(https?://|example\.com|google\.com|외부)" "$runbook" "$compose" 2>/dev/null; then
  echo "BLOCK: host proof guidance detected (external URL with network tool)"
  exit 1
fi
if grep -Eqi "(localhost|127\.0\.0\.1|0\.0\.0\.0).*(curl|wget|nc)" "$runbook" "$compose" 2>/dev/null; then
  echo "BLOCK: host proof guidance detected (localhost with network tool)"
  exit 1
fi

# 2) verify 자체가 네트워크를 시도하는 흔적이 있으면 BLOCK(방어적)
#    (이 파일 안에 curl/wget/nc가 실제 명령어로 사용되면 즉시 실패)
#    주석이나 검사 로직은 제외 (grep 패턴 자체는 허용)
if grep -vE "^[[:space:]]*#|grep.*curl|grep.*wget|grep.*nc" "$0" | grep -Eqi "(curl|wget|nc|telnet)[[:space:]]"; then
  echo "BLOCK: verify script must be decision-only (no network tools)"
  exit 1
fi

EGRESS_DENY_PROOF_HARNESS_V1_OK=1
EGRESS_DENY_RUNBOOK_V1_OK=1
EGRESS_DENY_PROOF_EXECUTES_IN_SANDBOX_OK=1
exit 0

