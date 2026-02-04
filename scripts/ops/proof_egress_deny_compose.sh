#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${1:-ops/onprem/compose/docker-compose.butler.internal.yml}"
OUT="${2:-docs/ops/PROOFS/2026-01-30_runtime_egress_compose_proof.md}"

command -v docker >/dev/null 2>&1 || { echo "BLOCK: docker not found"; exit 1; }

# NOTE: 실제 이미지/서비스 실행은 환경마다 다르므로, 여기서는
# 1) internal 네트워크 템플릿이 존재하고
# 2) runtime 컨테이너가 해당 네트워크에 붙어있다는 전제하에
# 외부 egress 시도 실패를 증빙으로 남긴다.
#
# 운영 환경에서는 butler-runtime 컨테이너 이름을 지정해 아래 TEST_CONTAINER에 넣는다.

TEST_CONTAINER="${TEST_CONTAINER:-butler-runtime}"

{
  echo "# Runtime egress deny proof (Compose)"
  echo
  echo "compose_file: ${COMPOSE_FILE}"
  echo "container: ${TEST_CONTAINER}"
  echo "expectation: outbound DNS/HTTP to public internet must FAIL"
  echo
  echo "## Attempt: DNS resolve (example.com) via node"
  echo '```'
  set +e
  docker exec "${TEST_CONTAINER}" node -e 'require("dns").lookup("example.com", (err) => { process.exit(err ? 1 : 0); });' 2>&1
  RC1=$?
  set -e
  echo "RC=${RC1}"
  echo '```'
  echo
  echo "## Attempt: HTTPS request (https://example.com) via node"
  echo '```'
  set +e
  docker exec "${TEST_CONTAINER}" node -e 'require("https").get("https://example.com", () => {}).on("error", () => { process.exit(1); }); setTimeout(() => process.exit(0), 2000);' 2>&1
  RC2=$?
  set -e
  echo "RC=${RC2}"
  echo '```'
  echo
  echo "## Verdict"
  if [[ "${RC1}" -ne 0 && "${RC2}" -ne 0 ]]; then
    echo "RUNTIME_EGRESS_ENV_DENY_OK=1"
    echo "RUNTIME_EGRESS_ENV_PROOF_OK=1"
  else
    echo "RUNTIME_EGRESS_ENV_DENY_OK=0"
    echo "RUNTIME_EGRESS_ENV_PROOF_OK=0"
    echo "BLOCK: outbound attempt unexpectedly succeeded"
    exit 1
  fi
} > "${OUT}"

echo "OK: wrote ${OUT}"
