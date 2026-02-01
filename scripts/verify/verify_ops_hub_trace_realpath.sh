#!/usr/bin/env bash
set -euo pipefail

OPS_HUB_TRACE_REALPATH_PERSISTED_OK=0
OPS_HUB_TRACE_REALPATH_JOINABLE_OK=0
OPS_HUB_TRACE_REALPATH_NO_RAW_OK=0
OPS_HUB_TRACE_REALPATH_IDEMPOTENT_OK=0

cleanup() {
  echo "OPS_HUB_TRACE_REALPATH_PERSISTED_OK=${OPS_HUB_TRACE_REALPATH_PERSISTED_OK}"
  echo "OPS_HUB_TRACE_REALPATH_JOINABLE_OK=${OPS_HUB_TRACE_REALPATH_JOINABLE_OK}"
  echo "OPS_HUB_TRACE_REALPATH_NO_RAW_OK=${OPS_HUB_TRACE_REALPATH_NO_RAW_OK}"
  echo "OPS_HUB_TRACE_REALPATH_IDEMPOTENT_OK=${OPS_HUB_TRACE_REALPATH_IDEMPOTENT_OK}"

  if [[ "${OPS_HUB_TRACE_REALPATH_PERSISTED_OK}" == "1" ]] && \
     [[ "${OPS_HUB_TRACE_REALPATH_JOINABLE_OK}" == "1" ]] && \
     [[ "${OPS_HUB_TRACE_REALPATH_NO_RAW_OK}" == "1" ]] && \
     [[ "${OPS_HUB_TRACE_REALPATH_IDEMPOTENT_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

OUT="$(node scripts/ops_hub/report_trace_realpath_sample.cjs 2>&1)" || { echo "BLOCK: trace realpath report failed"; echo "$OUT"; exit 1; }

# 1) persisted: inserted >= 1
echo "$OUT" | grep -nE 'persisted_inserted=[1-9]' >/dev/null || { echo "FAIL: persisted_inserted < 1"; exit 1; }
OPS_HUB_TRACE_REALPATH_PERSISTED_OK=1

# 2) joinable 결과 라인 1개 이상 + 카운트 >=1
echo "$OUT" | grep -nE 'JOIN_LINE request_id=.* joinable=true' >/dev/null || { echo "FAIL: missing join line"; exit 1; }
echo "$OUT" | grep -nE 'joinable=true_count=[1-9]' >/dev/null || { echo "FAIL: joinable true count < 1"; exit 1; }
OPS_HUB_TRACE_REALPATH_JOINABLE_OK=1

# 3) idempotent: noop >= 1 (중복 ingest가 저장되지 않았음을 최소 1회 증명)
echo "$OUT" | grep -nE 'idempotent_noop=[1-9]' >/dev/null || { echo "FAIL: idempotent_noop < 1"; exit 1; }
OPS_HUB_TRACE_REALPATH_IDEMPOTENT_OK=1

# 4) no-raw(대표 금지 패턴)
if echo "$OUT" | grep -nE '(raw_text|prompt|messages|document_body|content|BEGIN .* PRIVATE KEY|_TOKEN=|_PASSWORD=|DATABASE_URL=)' ; then
  echo "FAIL: raw/secret-like content detected"
  exit 1
fi
OPS_HUB_TRACE_REALPATH_NO_RAW_OK=1

exit 0

