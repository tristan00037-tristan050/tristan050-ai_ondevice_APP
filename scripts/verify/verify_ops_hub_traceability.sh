#!/usr/bin/env bash
set -euo pipefail

OPS_HUB_TRACEABILITY_OK=0
OPS_HUB_TRACEABILITY_REPORT_OK=0
OPS_HUB_TRACEABILITY_NO_RAW_OK=0

cleanup() {
  echo "OPS_HUB_TRACEABILITY_OK=${OPS_HUB_TRACEABILITY_OK}"
  echo "OPS_HUB_TRACEABILITY_REPORT_OK=${OPS_HUB_TRACEABILITY_REPORT_OK}"
  echo "OPS_HUB_TRACEABILITY_NO_RAW_OK=${OPS_HUB_TRACEABILITY_NO_RAW_OK}"
  if [[ "${OPS_HUB_TRACEABILITY_OK}" == "1" ]] && \
     [[ "${OPS_HUB_TRACEABILITY_REPORT_OK}" == "1" ]] && \
     [[ "${OPS_HUB_TRACEABILITY_NO_RAW_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

OUT="$(node scripts/ops_hub/report_traceability_sample.cjs 2>&1)" || { echo "BLOCK: trace report failed"; echo "$OUT"; exit 1; }

# 1) joinable 결과 라인 1개 이상 (문서 말이 아니라 출력 기반)
echo "$OUT" | grep -nE 'JOIN_LINE request_id=.* joinable=true' >/dev/null || { echo "FAIL: missing join line"; exit 1; }
echo "$OUT" | grep -nE 'joinable=true_count=[1-9]' >/dev/null || { echo "FAIL: joinable true count < 1"; exit 1; }
OPS_HUB_TRACEABILITY_REPORT_OK=1

# 2) no-raw(대표 금지 패턴)
if echo "$OUT" | grep -nE '(raw_text|prompt|messages|document_body|content|BEGIN .* PRIVATE KEY|_TOKEN=|_PASSWORD=|DATABASE_URL=)' ; then
  echo "FAIL: raw/secret-like content detected"
  exit 1
fi
OPS_HUB_TRACEABILITY_NO_RAW_OK=1

# 3) overall ok
OPS_HUB_TRACEABILITY_OK=1
exit 0

