#!/usr/bin/env bash
set -euo pipefail

OPS_REPORT_PIPELINE_V1_OK=0
OPS_REPORT_ARCHIVE_DATED_V1_OK=0

trap 'echo "OPS_REPORT_PIPELINE_V1_OK=${OPS_REPORT_PIPELINE_V1_OK}";
      echo "OPS_REPORT_ARCHIVE_DATED_V1_OK=${OPS_REPORT_ARCHIVE_DATED_V1_OK}"' EXIT

policy_dir="docs/ops/contracts"
workflow=".github/workflows/ops-reports-nightly.yml"
uploader="scripts/ops/upload_reports_v1.sh"
reports_dir="docs/ops/reports"
archive_dir="$reports_dir/archive"

# 존재 판정(판정만)
test -f "$workflow"  || { echo "BLOCK: missing ops-reports-nightly workflow"; exit 1; }
test -f "$uploader"  || { echo "BLOCK: missing upload_reports_v1.sh"; exit 1; }

# verify=판정만: 워크플로/스크립트 내에서 네트워크 도구 실행을 직접 쓰지 않도록 최소 방어(오탐 최소)
# (artifact 업로드는 actions/upload-artifact가 담당)
if grep -EIn '^[[:space:]]*(curl|wget|nc|telnet)[[:space:]]+' "$uploader" >/dev/null 2>&1; then
  echo "BLOCK: uploader must be decision-only (no network tool execution)"
  exit 1
fi

# 리포트 파일 경로 존재 규약(생성 자체는 ops 스크립트가 담당)
test -d "$reports_dir" || { echo "BLOCK: missing docs/ops/reports"; exit 1; }

# archive는 "정책상" 날짜별 누적이 목표이므로 디렉토리 존재를 요구(파일은 ops 실행에서 생성)
test -d "$archive_dir" || { echo "BLOCK: missing docs/ops/reports/archive"; exit 1; }

OPS_REPORT_PIPELINE_V1_OK=1
OPS_REPORT_ARCHIVE_DATED_V1_OK=1
exit 0
