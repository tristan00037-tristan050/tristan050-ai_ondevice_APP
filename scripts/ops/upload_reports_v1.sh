#!/usr/bin/env bash
set -euo pipefail

# OPS_REPORT_PIPELINE_UPLOAD_V1
# - 목적: 생성된 meta-only 리포트를 Actions artifact로 업로드하기 위한 "로컬/CI 공용" 준비 스크립트
# - 주의: 이 스크립트는 DoD 키를 출력하지 않습니다.
# - 주의: 비밀값/토큰/환경변수 출력 금지

src_dir="docs/ops/reports"
test -d "$src_dir" || { echo "BLOCK: missing docs/ops/reports"; exit 1; }

# 최소 요구 파일: 이미 P4에서 생성되는 최신 리포트
test -f "$src_dir/repo_contracts_latest.json" || { echo "BLOCK: missing repo_contracts_latest.json"; exit 1; }
test -f "$src_dir/repo_contracts_latest.md"   || { echo "BLOCK: missing repo_contracts_latest.md"; exit 1; }
test -f "$src_dir/ai_smoke_latest.json"       || { echo "BLOCK: missing ai_smoke_latest.json"; exit 1; }
test -f "$src_dir/ai_smoke_latest.md"         || { echo "BLOCK: missing ai_smoke_latest.md"; exit 1; }

# archive dated 파일은 있으면 확인(없으면 가드에서 BLOCK 여부 결정)
test -d "$src_dir/archive" || true

exit 0
