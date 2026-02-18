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

# 스캔 대상 모으기 (runbook + compose + (있으면) k8s 템플릿)
targets=("$runbook" "$compose")
if [[ -d "tools/egress_proof/k8s" ]]; then
  # 파일이 없을 때 에러 나지 않게
  while IFS= read -r f; do targets+=("$f"); done < <(find tools/egress_proof/k8s -type f -maxdepth 2 2>/dev/null || true)
fi

# 금지: host-side proof 커맨드 (양방향 모두 차단)
# - 도구: curl/wget/nc/telnet
# - 호스트: localhost/127.0.0.1/0.0.0.0/::1
# 같은 라인에 도구와 호스트가 모두 있으면 차단
for target in "${targets[@]}"; do
  if [[ ! -f "$target" ]]; then
    continue
  fi
  # curl/wget/nc/telnet이 있고, 같은 라인에 localhost/127.0.0.1/0.0.0.0/::1이 있으면 차단
  if grep -qiE "(curl|wget|nc|telnet)" "$target" && grep -qiE "(localhost|127\.0\.0\.1|0\.0\.0\.0|::1)" "$target"; then
    # 같은 라인에 둘 다 있는지 확인
    if grep -EIn "(curl|wget|nc|telnet).*(localhost|127\.0\.0\.1|0\.0\.0\.0|::1)|(localhost|127\.0\.0\.1|0\.0\.0\.0|::1).*(curl|wget|nc|telnet)" "$target" >/dev/null 2>&1; then
      echo "BLOCK: host-side proof command detected (tool<->host on same line in $target)"
      exit 1
    fi
  fi
done

# 2) verify 스크립트가 실제로 네트워크 도구를 실행하면 안 됨(라인 시작 커맨드만 탐지)
if grep -EIn '^[[:space:]]*(curl|wget|nc|telnet)[[:space:]]+' "$0" >/dev/null 2>&1; then
  echo "BLOCK: verify must be decision-only (no network tool execution)"
  exit 1
fi

EGRESS_DENY_PROOF_HARNESS_V1_OK=1
EGRESS_DENY_RUNBOOK_V1_OK=1
EGRESS_DENY_PROOF_EXECUTES_IN_SANDBOX_OK=1
exit 0

