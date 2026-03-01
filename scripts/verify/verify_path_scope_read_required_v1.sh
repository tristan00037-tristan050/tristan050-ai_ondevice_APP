#!/usr/bin/env bash
set -euo pipefail

PATH_SCOPE_READ_REQUIRED_OK=0
finish(){ echo "PATH_SCOPE_READ_REQUIRED_OK=${PATH_SCOPE_READ_REQUIRED_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/PATH_SCOPE_SSOT_V1.txt"

# SSOT 존재는 필수(없으면 fail-closed)
test -f "$SSOT" || { echo "ERROR_CODE=PATH_SCOPE_SSOT_MISSING"; exit 1; }

# 최소 대상(오탐 방지: add-only로 확장)
# "스캐너류" 또는 "정적 검사"에서 경로 드리프트가 치명적인 것만 먼저 강제
TARGETS=(
  "scripts/verify/verify_meta_only_output_guard_v1.sh"
  "scripts/verify/verify_verify_purity_full_scope_v2.sh"
)

missing=0
for f in "${TARGETS[@]}"; do
  test -f "$f" || { echo "ERROR_CODE=TARGET_MISSING"; echo "TARGET=${f}"; exit 1; }

  # 스크립트가 PATH_SCOPE SSOT를 읽었음을 나타내는 메타 토큰을 출력해야 함
  # 주석/문자열에만 있어서는 안 되므로, 'echo PATH_SCOPE_SSOT_READ_OK=1' 또는 동등한 출력이 실제 코드에 존재해야 함
  if ! grep -Eq '^[[:space:]]*echo[[:space:]]+"?PATH_SCOPE_SSOT_READ_OK=1' "$f"; then
    echo "ERROR_CODE=PATH_SCOPE_SSOT_READ_TOKEN_MISSING"
    echo "TARGET=${f}"
    missing=1
  fi
done

[ "$missing" = "0" ] || exit 1

PATH_SCOPE_READ_REQUIRED_OK=1
exit 0
