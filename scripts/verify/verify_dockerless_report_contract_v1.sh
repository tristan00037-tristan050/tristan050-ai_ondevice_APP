#!/usr/bin/env bash
set -euo pipefail

DOCKERLESS_REPORT_RUN_OK=0
DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=0
DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=0

finish() {
  echo "DOCKERLESS_REPORT_RUN_OK=${DOCKERLESS_REPORT_RUN_OK}"
  echo "DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=${DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK}"
  echo "DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=${DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK}"
}
trap finish EXIT

# 단일 경로 계약: gen_repo_guard_report_v1.sh와 동일 (REPO_GUARD_REPORTS_ROOT, default docs/ops/reports)
# 1) REPO_GUARD_REPORTS_ROOT (generator와 동일)
# 2) docs/ops/reports (generator default)
# 3) OUT_ROOT/ops/reports (호환 폴백)
REPORT_ROOT="${REPO_GUARD_REPORTS_ROOT:-docs/ops/reports}"
report="${REPORT_ROOT}/repo_contracts_latest.json"
if [ ! -f "$report" ]; then
  report="${OUT_ROOT:-out}/ops/reports/repo_contracts_latest.json"
fi
if [ ! -f "$report" ]; then
  report="docs/ops/reports/repo_contracts_latest.json"
fi

# keys-only 모드(리포트 생성 중)에서는 리포트가 아직 없을 수 있음 → 0 출력 후 성공
if [ ! -f "$report" ]; then
  if [[ "${REPO_GUARD_KEYS_ONLY:-0}" == "1" ]]; then
    DOCKERLESS_REPORT_RUN_OK=0
    DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=0
    DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=0
    exit 0
  fi
  echo "ERROR_CODE=REPORT_MISSING"
  exit 1
fi

node - "$report" <<'NODE'
const fs = require("fs");

// node - "$report" 형태는 환경에 따라 argv[1]이 "-"가 될 수 있어 보강
const a1 = process.argv[1];
const a2 = process.argv[2];
const reportPath = (!a1 || a1 === "-") ? a2 : a1;
if (!reportPath) process.exit(20);

const j = JSON.parse(fs.readFileSync(reportPath, "utf8"));
const keys = (j && j.keys) || {};

function is01(v){ return v === "0" || v === "1"; }
function must01(k){
  if(!(k in keys)) process.exit(21);
  if(!is01(keys[k])) process.exit(22);
}

must01("DOCKER_IT_NET_DB_SVCNAME_V1_OK");
must01("HOST_DOCKER_INTERNAL_FORBIDDEN_OK");
process.exit(0);
NODE

DOCKERLESS_REPORT_RUN_OK=1
DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=1
DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=1
exit 0
